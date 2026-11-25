"""Own the one replay worker and publish immutable, completed frame records."""

import json
import logging
from contextlib import closing
from pathlib import Path
from threading import Condition, Lock, Thread
from time import perf_counter
from uuid import uuid4
from zipfile import BadZipFile

import numpy as np
import shapefile
from rasterio.warp import transform

from . import comparison, history, observed
from .data import SEOUL_CRS, utc
from .simulation import SimulationSession

LOG = logging.getLogger("antiflood.replay")


def gauge_list(gauges):
    lons, lats = transform(SEOUL_CRS, "EPSG:4326", [g[1] for g in gauges], [g[2] for g in gauges])
    return [
        {"id": code, "name": name, "lon": round(lon, 6), "lat": round(lat, 6)}
        for (code, _, _, name), lon, lat in zip(gauges, lons, lats)
    ]


class ReplayConflict(Exception):
    pass


class Replay:
    def __init__(self, grid, tiles, engine, gauge_map, gauges, scenarios, rasters, output, threads, frame_wait):
        self.grid = grid
        self.tiles = tiles
        self.engine = engine
        self.gauge_map = gauge_map
        self.gauges = gauges
        self.scenarios = {scenario.id: scenario for scenario in scenarios}
        self.rasters = rasters
        self.output = output
        self.threads = threads
        self.frame_wait = frame_wait
        self.condition = Condition()
        self.commands = Lock()
        self.settings = None
        self.mode = "compare"
        self.thread = None
        self._reset()

    def _reset(self):
        self.status = "ready"
        self.run_id = self.scenario_id = self.simulated_time = self.error = None
        self.stop = self.pause_requested = False
        self.frames = []
        self.progress = 0
        self.prepared = False
        self.phase = self.reference_id = None

    def state(self):
        with self.condition:
            latest = self.frames[-1] if self.frames else {}
            return {
                "status": self.status,
                "mode": self.phase,
                "reference_id": self.reference_id,
                "settings": self.settings,
                "progress": getattr(self, "progress", 0),
                "scenario_id": self.scenario_id,
                "run_id": self.run_id,
                "simulated_time_utc": self.simulated_time,
                "latest_frame_id": latest.get("id"),
                "latest_frame": latest,
                "frame_count": len(self.frames),
                "active_tile_count": latest.get("active_tile_count", 0),
                "max_depth_m": latest.get("max_depth_m"),
                "frame_source": "computed" if latest else None,
                "error": self.error,
            }

    def list_frames(self, offset):
        with self.condition:
            return {"run_id": self.run_id, "frames": self.frames[offset:]}

    def command(self, operation, scenario_id=None):
        with self.commands:
            with self.condition:
                if operation == "start":
                    if self.status in ("running", "paused"):
                        raise ReplayConflict("진행 중인 재생을 먼저 초기화해 주세요.")
                    scenario = self.scenarios[scenario_id]
                    self._reset()
                    self.run_id = uuid4().hex
                    self.scenario_id = scenario.id
                    self.status = "running"
                    self.simulated_time = utc(scenario.start)
                    self.thread = Thread(target=self._worker, args=(scenario, self.run_id), daemon=True)
                    self.thread.start()
                    self.condition.wait_for(lambda: self.prepared or self.status == "error")
                elif operation == "pause":
                    if self.status != "running":
                        raise ReplayConflict("계산 중일 때 일시정지할 수 있습니다.")
                    self.pause_requested = True
                    self.condition.notify_all()
                    self.condition.wait_for(lambda: self.status != "running")
                elif operation == "resume":
                    if self.status != "paused":
                        raise ReplayConflict("일시정지한 재생만 이어갈 수 있습니다.")
                    self.pause_requested = False
                    self.status = "running"
                    self.condition.notify_all()
                elif operation == "reset":
                    self.stop = True
                    self.condition.notify_all()
                    thread = self.thread
            if operation == "reset":
                if thread:
                    thread.join()
                with self.condition:
                    self.thread = None
                    self._reset()
            return self.state()

    def _checkpoint(self, wait=0):
        with self.condition:
            if wait:
                self.condition.wait_for(lambda: self.stop or self.pause_requested, wait)
            if self.pause_requested and not self.stop:
                self.status = "paused"
                self.condition.notify_all()
                self.condition.wait_for(lambda: self.stop or not self.pause_requested)
            return not self.stop

    def _worker(self, scenario, run_id):
        directory = self.output / run_id
        try:
            conditions = comparison.run_conditions(self.grid, self.gauge_map, scenario, self.threads, self.engine)
            reference = None
            if self.mode == "compare":
                reference = comparison.reusable_reference(self.output, conditions)
                if reference is None:
                    directory = self.output / uuid4().hex
                    if not self._calculate(scenario, directory, "reference", conditions):
                        return
                    reference = directory
                directory = self.output / run_id
            elif self.mode == "streaming":
                reference = comparison.reusable_reference(self.output, conditions)
            mode = "reference" if self.mode == "reference" else "streaming"
            if self._calculate(scenario, directory, mode, conditions, reference):
                with self.condition:
                    self.status = "completed"
                    self.condition.notify_all()
                LOG.info("Replay completed: %s", directory.name)
        except Exception as exc:
            LOG.exception("Replay failed: %s", directory.name)
            with self.condition:
                self.status = "error"
                if isinstance(exc, OSError):
                    self.error = "결과 파일을 저장하지 못했습니다. 출력 폴더의 쓰기 권한과 남은 용량을 확인해 주세요."
                elif isinstance(exc, (ValueError, RuntimeError)):
                    self.error = str(exc)
                else:
                    self.error = "계산이 중단되었습니다. 터미널 로그를 확인한 뒤 재생을 다시 시작해 주세요."
                self.condition.notify_all()
            self._save_status(directory, "error", self.error)

    def _calculate(self, scenario, directory, mode, conditions, reference=None):
        directory.mkdir(parents=True)
        np.save(directory / "valid.npy", self.grid.valid)
        np.save(directory / "gauge_map.npy", self.gauge_map)
        if self.grid.drain_mm_h is not None:
            np.savez_compressed(directory / "drainage.npz", rate=self.grid.drain_mm_h, source=self.grid.drain_class)
        metadata = {
            "scenario": scenario.summary(),
            "settings": self.settings,
            "status": "running",
            "mode": mode,
            "calculation_policy": "full_grid_synchronous",
            "conditions": conditions,
            "reference_id": reference.name if reference else None,
            "map": self.rasters.metadata(),
            "gauges": gauge_list(self.gauges),
            "rainfall_distribution": "nearest_station; constant_within_observed_interval",
            "engine": "CADDIES outflowWCA2Dv1",
            "manning": 0.04,
            "threads_requested": self.threads,
        }
        history.write_json(directory / "run.json", metadata)
        if mode == "streaming":
            np.save(directory / "tile_map.npy", self.tiles.by_cell.reshape(self.grid.valid.shape))
        session = SimulationSession(
            self.grid, self.tiles, self.engine, self.gauge_map, len(self.gauges),
            scenario.start, self.threads, mode,
        )
        with self.condition:
            self.run_id = directory.name
            self.phase = mode
            self.reference_id = metadata["reference_id"]
            self.frames = []
            self.progress = 0
            self.simulated_time = utc(session.time)
            self.prepared = True
            self.condition.notify_all()
        calculation = storage = comparison_seconds = 0.0
        index = 0
        with closing(scenario.iter_intervals()) as intervals:
            for interval in intervals:
                if not self._checkpoint():
                    self._save_status(directory, "stopped")
                    return False
                started = perf_counter()
                session.set_rain(interval)
                while not session.advance_step():
                    pass
                latency = perf_counter() - started
                calculation += latency
                frame, stored, compared = self._publish(
                    directory, session, index, latency, calculation, reference,
                )
                session.interval = None
                del interval
                storage += stored
                comparison_seconds += compared
                index += 1
                with self.condition:
                    self.frames.append(frame)
                    self.simulated_time = frame["time"]
                    self.progress = index / scenario.interval_count
                if index < scenario.interval_count and not self._checkpoint(self.frame_wait):
                    self._save_status(directory, "stopped")
                    return False

        if index != scenario.interval_count or session.time != scenario.end:
            raise ValueError("강우 입력의 구간 수 또는 종료 시각이 시나리오와 다릅니다.")

        started = perf_counter()
        maximum = session.maximum_depth.reshape(self.grid.valid.shape)
        np.savez_compressed(directory / "maximum.npz", depth=maximum.astype(np.float32))
        metadata.update(
            status="completed", calculation_seconds=calculation,
            storage_seconds=storage + perf_counter() - started,
            comparison_seconds=comparison_seconds,
            cumulative_cell_updates=int(session.cell_steps),
            maximum_depth_m=float(maximum.max()),
        )
        if reference:
            info = json.loads((reference / "run.json").read_text(encoding="utf-8"))
            metadata["performance"] = comparison.performance(info, metadata)
        try:
            metadata["observed_overlap"] = observed.observed_overlap(
                self.rasters.dataset, self.grid, maximum, comparison.FLOOD_THRESHOLD_M,
            )
        except (OSError, ValueError, BadZipFile, shapefile.ShapefileException) as exc:
            metadata["observed_overlap"] = None
            metadata["observed_error"] = "침수흔적도 원본을 읽지 못했습니다."
            LOG.warning("Observed footprint unavailable (%s)", type(exc).__name__)
        history.write_json(directory / "run.json", metadata)
        return True

    def _save_status(self, directory, status, error=None):
        metadata = directory / "run.json"
        if not metadata.exists():
            return
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data.update(status=status, error=error)
        pending = directory / "run.tmp"
        pending.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        pending.replace(metadata)

    def _publish(self, directory: Path, session, index, latency, calculation, reference):
        water, error = session.verify()
        stem = f"{index:05d}"
        frame_id = f"{directory.name}_{stem}"
        frame = {
            "id": frame_id,
            "mode": session.mode,
            "calculation_policy": "full_grid_synchronous",
            "last_step_seconds": session.last_step_seconds,
            "time": utc(session.time),
            "rain_observed_at": utc(session.interval.observed_at),
            "rain_interval_mm": session.interval.gauge_mm.tolist(),
            "rain_max_mm": float(session.interval.gauge_mm.max()),
            "max_depth_m": float(session.depth.max()),
            "active_tile_count": int(session.active_tiles.size),
            "active_tile_ratio": float(session.active_tiles.size / len(self.tiles.ids)),
            "active_cell_count": int(session.active_cell_count),
            "cumulative_cell_updates": int(session.cell_steps),
            "worker_count": session.worker_count,
            "rain_m3": float(session.rain_m3),
            "drain_m3": float(session.drain_m3),
            "boundary_outflow_m3": float(session.boundary_outflow_m3),
            "water_m3": water,
            "mass_error_m3": error,
            "calculation_seconds": calculation,
            "update_latency_seconds": latency,
            "frame_source": "computed",
        }
        depth = session.depth.reshape(self.grid.valid.shape).astype(np.float32)
        extra = {}
        if session.mode == "streaming":
            frame["sliding_mm"] = session.history.hour_mm.tolist()
            frame["decaying_mm"] = session.history.decay_mm.tolist()
            extra = {
                "tile_modes": session.tile_modes,
                "tile_reasons": session.tile_reasons,
                "last_update": session.last_update.astype(np.float32),
            }
        compared = 0.0
        if reference:
            started = perf_counter()
            match = json.loads((reference / f"{stem}.json").read_text(encoding="utf-8"))
            if match["time"] != frame["time"]:
                raise ValueError("비교하려는 두 수심 배열의 계산 시각이 다릅니다.")
            if match["worker_count"] != frame["worker_count"]:
                raise ValueError("두 계산 모드에서 실제로 사용한 OpenMP 스레드 수가 다릅니다.")
            frame["reference_frame_id"] = match["id"]
            frame["comparison"] = {
                **comparison.accuracy(history.load_depth(reference, stem), depth, self.grid.valid),
                **comparison.performance(match, frame),
                "reference_seconds": match["calculation_seconds"],
                "reference_cell_updates": match["cumulative_cell_updates"],
            }
            compared = perf_counter() - started
        started = perf_counter()
        np.savez_compressed(directory / f"{stem}.npz", depth=depth, **extra)
        history.write_json(directory / f"{stem}.json", frame)
        return frame, perf_counter() - started, compared

    def point(self, directory, stem, longitude, latitude):
        x, y = transform("EPSG:4326", SEOUL_CRS, [longitude], [latitude])
        col, row = (~self.grid.affine) * (x[0], y[0])
        i, j = int(np.floor(row)), int(np.floor(col))
        height, width = self.grid.valid.shape
        if not (0 <= i < height and 0 <= j < width and self.grid.valid[i, j]):
            return None
        return self.tile(directory, stem, self.tiles.by_cell[i * width + j], i, j)

    def tile(self, directory, stem, index, row=None, col=None):
        meta = json.loads((directory / f"{stem}.json").read_text(encoding="utf-8"))
        depth = history.load_depth(directory, stem)
        cells = self.tiles.members[index]
        values = depth.ravel()[cells]
        tile_id = self.tiles.ids[index]
        gauge_indices = self.gauge_map.ravel()[cells]
        if row is not None:
            gauge_indices = [self.gauge_map[row, col]]
        return {
            "tile_id": tile_id,
            "active": history.tile_active(directory, stem, meta, index, tile_id),
            "time": meta["time"],
            "depth_m": float(depth[row, col]) if row is not None else None,
            "min_tile_depth_m": float(values.min()),
            "max_tile_depth_m": float(values.max()),
            "rain": [
                {"station_id": self.gauges[i][0], "name": self.gauges[i][3], "mm": meta["rain_interval_mm"][i]}
                for i in np.unique(gauge_indices)
            ],
        }
