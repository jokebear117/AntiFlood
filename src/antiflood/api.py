"""Run the local API and serve the static MapLibre dashboard."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import re
from typing import Annotated, Literal
from threading import Lock
from zipfile import BadZipFile

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, ConfigDict, Field
import shapefile
from starlette.middleware.trustedhost import TrustedHostMiddleware
import uvicorn

from . import agent, history
from .data import ROOT, dataset_dir, load_gauges, load_grid, load_scenarios, DEFAULT_BOUNDS, dem_paths
from .frames import MapRasters
from .replay import Replay, ReplayConflict
from .simulation import NativeEngine
from .tiles import TileGrid

LOG = logging.getLogger("antiflood")
FRAME_PATTERN = re.compile(r"([0-9a-f]{32})_([0-9]{5})")
WEB = ROOT / "web"


@asynccontextmanager
async def lifespan(app):
    load_dotenv(ROOT / ".env")
    output = Path(os.getenv("ANTIFLOOD_OUTPUT", ROOT / "outputs")).resolve()
    app.state.frame_root = output / "frames"
    app.state.configuration_lock = Lock()
    app.state.dataset = dataset_dir()
    app.state.replay = app.state.rasters = None
    app.state.catalog = []
    errors = []
    engine = None
    try:
        engine = NativeEngine()
    except (OSError, AttributeError) as exc:
        LOG.exception("Native engine is unavailable")
        errors.append(f"계산 엔진을 불러오지 못했습니다. README의 빌드와 실행 경로를 확인해 주세요. ({exc})")
    app.state.engine = engine
    app.state.engine_ready = engine is not None
    try:
        dataset = dataset_dir()
        grid = load_grid(dataset)
        app.state.rasters = MapRasters(grid, dataset)
        gauges, gauge_map = load_gauges(dataset, grid)
        app.state.catalog = load_scenarios(dataset, gauges)
        app.state.gauges = [{"id": code, "name": name} for code, _, _, name in gauges]
        threads = int(os.getenv("ANTIFLOOD_THREADS", "4"))
        wait = float(os.getenv("ANTIFLOOD_FRAME_WAIT", "0.15"))
        if not 1 <= threads <= 64 or not 0 <= wait <= 10:
            raise ValueError("스레드 수는 1~64, 결과 표시 대기는 0~10초로 지정해 주세요.")
        if engine is not None:
            app.state.replay = Replay(
                grid, TileGrid(grid), engine, gauge_map, gauges, app.state.catalog,
                app.state.rasters, app.state.frame_root, threads, wait,
            )
    except (OSError, ValueError, KeyError, StopIteration, BadZipFile, shapefile.ShapefileException) as exc:
        LOG.exception("Input or configuration could not be loaded")
        errors.append(f"지형, 강우 또는 실행 설정을 읽을 수 없습니다. README의 데이터 준비를 확인해 주세요. ({exc})")
    app.state.startup_error = " ".join(errors) or None
    try:
        yield
    finally:
        if app.state.replay:
            app.state.replay.command("reset")


app = FastAPI(title="Anti-Flood", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
app.mount("/assets", StaticFiles(directory=WEB), name="assets")


@app.middleware("http")
async def same_origin_commands(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "로컬 대시보드에서 요청해 주세요."}, status_code=403)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    state = app.state
    return {
        "status": "ok",
        "application": "antiflood",
        "engine_ready": state.engine_ready,
        "data_ready": bool(state.catalog),
        "replay_ready": state.replay is not None,
        "map_ready": (WEB / "vendor/maplibre-gl.mjs").is_file(),
        "agent_ready": bool(agent.solar_key()),
        "error": state.startup_error,
    }


@app.get("/api/scenarios")
def scenarios():
    return [scenario.summary() for scenario in app.state.catalog]


def replay_or_503():
    if app.state.replay is None:
        raise HTTPException(503, app.state.startup_error or "계산을 시작할 수 없습니다.")
    return app.state.replay


@app.get("/api/map")
def map_metadata():
    if not app.state.rasters:
        raise HTTPException(503, app.state.startup_error or "지형 자료를 읽을 수 없습니다.")
    return {**app.state.rasters.metadata(), "gauges": getattr(app.state, "gauges", []),
            "dem_bounds": [[126 if "E126" in path.name else 127,37,127 if "E126" in path.name else 128,38] for path in dem_paths(app.state.dataset)],
            "selection_bounds": [126.7,37.4,127.2,37.72], "max_cells":1_000_000}


@app.get("/api/terrain/{zoom}/{x}/{y}.png")
def terrain(zoom: int, x: int, y: int):
    if not app.state.rasters:
        raise HTTPException(503, "표시할 지형 자료가 없습니다.")
    if not 0 <= zoom <= 13 or not 0 <= x < 2**zoom or not 0 <= y < 2**zoom:
        raise HTTPException(404, "지형 타일을 찾을 수 없습니다.")
    return Response(
        app.state.rasters.terrain_png(zoom, x, y),
        media_type="image/png", headers={"Cache-Control": "public, max-age=3600"},
    )


class RunSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bounds: tuple[float, float, float, float] = DEFAULT_BOUNDS
    drain_mm_h: float = Field(default=5, ge=0, le=500, allow_inf_nan=False)
    threads: int = Field(default=4, ge=1, le=64)
    boundary: Literal["open", "closed"] = "open"


class StartRequest(RunSettings):
    scenario_id: str


def prepare_region(settings):
    grid = load_grid(app.state.dataset, bounds=settings.bounds, drain_mm_h=settings.drain_mm_h,
                     boundary=settings.boundary, use_drain_raster=False)
    gauges, mapping = load_gauges(app.state.dataset, grid)
    scenarios = load_scenarios(app.state.dataset, gauges)
    return grid, gauges, mapping, scenarios


@app.post("/api/region")
def region(settings: RunSettings):
    try:
        grid, gauges, mapping, catalog = prepare_region(settings)
        return {"map":MapRasters(grid, app.state.dataset).metadata(),
                "scenarios":[item.summary() for item in catalog],
                "gauges":[{"id":g[0],"name":g[3]} for g in gauges],
                "estimated_memory_mb":round(grid.valid.size * 160 / 1_000_000),
                "warning":"넓은 영역은 계산과 결과 저장에 더 오래 걸립니다." if grid.valid.size > 200_000 else None}
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/simulation/start")
def start(body: StartRequest):
    if app.state.engine is None:
        raise HTTPException(503, app.state.startup_error)
    with app.state.configuration_lock:
        previous = app.state.replay
        if previous and previous.state()["status"] in ("running", "paused"):
            raise HTTPException(409, "진행 중인 실행을 먼저 초기화해 주세요.")
        try:
            grid, gauges, mapping, catalog = prepare_region(body)
            if body.scenario_id not in {item.id for item in catalog}:
                raise ValueError("선택 영역의 강우 시나리오를 다시 확인해 주세요.")
            rasters = MapRasters(grid, app.state.dataset)
            replay = Replay(grid, TileGrid(grid), app.state.engine, mapping, gauges, catalog,
                            rasters, app.state.frame_root, body.threads,
                            float(os.getenv("ANTIFLOOD_FRAME_WAIT", "0.15")))
            replay.settings = RunSettings(**body.model_dump(exclude={"scenario_id"})).model_dump(mode="json")
            app.state.replay = replay
            return replay.command("start", body.scenario_id)
        except (ValueError, OSError, KeyError, StopIteration) as exc:
            raise HTTPException(422, str(exc)) from exc


@app.post("/api/simulation/pause")
def pause():
    return perform("pause")


@app.post("/api/simulation/resume")
def resume():
    return perform("resume")


@app.post("/api/simulation/reset")
def reset():
    return perform("reset")


def perform(operation, scenario_id=None):
    try:
        with app.state.configuration_lock:
            return replay_or_503().command(operation, scenario_id)
    except ReplayConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/api/simulation/state")
def simulation_state():
    if app.state.replay:
        return app.state.replay.state()
    return {
        "status": "error" if app.state.startup_error else "idle",
        "error": app.state.startup_error, "frame_count": 0,
    }


@app.get("/api/simulation/frames")
def simulation_frames(offset: Annotated[int, Query(ge=0)] = 0):
    return replay_or_503().list_frames(offset)


def frame_file(frame_id):
    match = FRAME_PATTERN.fullmatch(frame_id)
    if match:
        run_id, stem = match.groups()
        directory = app.state.frame_root / run_id
        if (directory / f"{stem}.json").is_file():
            return directory, stem
    raise HTTPException(404, "계산 결과를 찾을 수 없습니다.")


@app.get("/api/frames/{frame_id}.png")
def frame_image(frame_id: str):
    directory, stem = frame_file(frame_id)
    return FileResponse(
        directory / f"{stem}.png", media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400, immutable"},
    )


@app.get("/api/frames/{frame_id}/point")
def frame_point(
    frame_id: str,
    lon: Annotated[float, Query(ge=-180, le=180)],
    lat: Annotated[float, Query(ge=-85, le=85)],
):
    directory, stem = frame_file(frame_id)
    try:
        point = history.saved_point(directory, stem, lon, lat)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if point is None:
        raise HTTPException(404, "선택한 위치는 계산 범위 밖입니다.")
    return point


@app.get("/api/runs")
def runs():
    result = []
    for path in sorted(app.state.frame_root.glob("*/run.json"), key=lambda p:p.stat().st_mtime, reverse=True):
        try:
            info, frames = history.read_run(app.state.frame_root, path.parent.name)
            result.append({"id":path.parent.name, "scenario":info["scenario"], "settings":info.get("settings"),
                           "map":info["map"], "status":info.get("status", "archived"), "frame_count":len(frames)})
        except (ValueError, OSError, KeyError):
            continue
    return result


@app.get("/api/runs/{run_id}")
def saved_run(run_id: str):
    try:
        info, frames = history.read_run(app.state.frame_root, run_id)
        live = app.state.replay.state() if app.state.replay else {}
        status = live.get("status") if live.get("run_id") == run_id else info.get("status", "archived")
        if status in ("running", "paused") and live.get("run_id") != run_id:
            status = "interrupted"
        return {**info, "id":run_id, "status":status, "frames":frames}
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(404, "저장된 실행을 읽을 수 없습니다.") from exc


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.post("/api/agent/query")
def question(body: Question):
    if not agent.solar_key():
        raise HTTPException(503, "UPSTAGE_API_KEY를 설정하고 서버를 다시 실행해 주세요.")
    replay = replay_or_503()
    ask = body.question.strip()
    if not ask:
        raise HTTPException(422, "질문을 입력해 주세요.")
    captured = {
        **replay.state(),
        "drainage_source": replay.grid.drainage_source,
        "assumed_drain_mm_h": replay.grid.default_drain_mm_h,
    }

    def tile(tile_id):
        index = replay.tiles.lookup.get(tile_id)
        if index is None or not captured["latest_frame_id"]:
            return None
        directory, stem = frame_file(captured["latest_frame_id"])
        return replay.tile(directory, stem, index)

    try:
        return {"answer": agent.answer(ask, lambda: captured, tile)}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError) as exc:
        # An upstream error can contain credential or request information.
        LOG.warning("Solar query failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Solar 응답을 받지 못했습니다. API 키, 모델 이름, 네트워크를 확인해 주세요.") from None


def main():
    load_dotenv(ROOT / ".env")
    log_format = "%(asctime)s %(levelname)s %(name)s %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)
    log_dir = Path(os.getenv("ANTIFLOOD_OUTPUT", ROOT / "outputs")).resolve() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = logging.FileHandler(log_dir / "antiflood.log", encoding="utf-8")
        log_file.setFormatter(logging.Formatter(log_format))
        LOG.addHandler(log_file)
    except OSError:
        LOG.warning("Cannot write the replay log. Logging to the terminal.")
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("ANTIFLOOD_PORT", "8000")))


if __name__ == "__main__":
    main()
