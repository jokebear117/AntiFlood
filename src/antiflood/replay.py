"""Own the one replay worker and publish immutable, completed frame records."""

from datetime import timedelta
import json
import logging
from pathlib import Path
from threading import Condition, Lock, Thread
from uuid import uuid4

import numpy as np
from rasterio.warp import transform

from .data import SEOUL_CRS, utc
from .simulation import SimulationSession

LOG = logging.getLogger("antiflood.replay")


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
        self.thread = None
        self._reset()

    def _reset(self):
        self.status = "ready"
        self.run_id = self.scenario_id = self.simulated_time = self.error = None
        self.stop = self.pause_requested = False
        self.frames = []

    def state(self):
        with self.condition:
            latest = self.frames[-1] if self.frames else {}
            return {
                "status": self.status,
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
                    self.simulated_time = utc(scenario.intervals[0].start)
                    self.thread = Thread(target=self._worker, args=(scenario, self.run_id), daemon=True)
                    self.thread.start()
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
        try:
            directory = self.output / run_id
            directory.mkdir(parents=True)
            np.save(directory / "valid.npy", self.grid.valid)
            (directory / "run.json").write_text(json.dumps({
                "scenario": scenario.summary(),
                "map": self.rasters.metadata(),
                "gauges": [{"id": code, "name": name} for code, _, _, name in self.gauges],
                "rainfall_distribution": "nearest_station; constant_within_observed_interval",
                "engine": "CADDIES outflowWCA2Dv1",
                "manning": 0.04,
                "threads_requested": self.threads,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            session = SimulationSession(
                self.grid, self.tiles, self.engine, self.gauge_map, len(self.gauges),
                scenario.intervals[0].start, self.threads,
            )
            drawn_at = session.time
            previous_rain = np.zeros(len(self.gauges))
            drawn_depth = session.depth.copy()
            for index, interval in enumerate(scenario.intervals):
                session.set_rain(interval)
                strongest = interval.gauge_mm.max()
                rising = (interval.gauge_mm - previous_rain).max() >= 0.5
                while self._checkpoint():
                    ended = session.advance_step()
                    with self.condition:
                        self.simulated_time = utc(session.time)
                    change = np.max(np.abs(session.depth - drawn_depth))
                    if strongest >= 5 or change >= 0.05:
                        cadence = 5
                    elif rising:
                        cadence = 10
                    elif strongest > 0 or change >= 0.005:
                        cadence = 30
                    else:
                        cadence = 60
                    final = ended and index + 1 == len(scenario.intervals)
                    if (
                        final or session.time - drawn_at >= timedelta(minutes=cadence)
                        or (ended and not self.frames)
                    ):
                        self._publish(directory, session)
                        drawn_at = session.time
                        drawn_depth = session.depth.copy()
                        if not final and not self._checkpoint(self.frame_wait):
                            return
                    if ended:
                        break
                else:
                    return
                session.verify()
                previous_rain = interval.gauge_mm
            with self.condition:
                self.status = "completed"
                self.condition.notify_all()
            LOG.info("Replay completed: %s", run_id)
        except Exception as exc:
            LOG.exception("Replay failed: %s", run_id)
            with self.condition:
                self.status = "error"
                if isinstance(exc, OSError):
                    self.error = "결과 파일을 저장하지 못했습니다. 출력 폴더의 쓰기 권한과 남은 용량을 확인해 주세요."
                elif isinstance(exc, (ValueError, RuntimeError)):
                    self.error = str(exc)
                else:
                    self.error = "계산이 중단되었습니다. 터미널 로그를 확인한 뒤 재생을 다시 시작해 주세요."
                self.condition.notify_all()

    def _publish(self, directory: Path, session):
        water, error = session.verify()
        stem = f"{len(self.frames):05d}"
        frame_id = f"{directory.name}_{stem}"
        frame = {
            "id": frame_id,
            "time": utc(session.time),
            "rain_observed_at": utc(session.interval.observed_at),
            "rain_interval_mm": session.interval.gauge_mm.tolist(),
            "rain_max_mm": float(session.interval.gauge_mm.max()),
            "max_depth_m": float(session.depth.max()),
            "active_tile_count": int(session.active_tiles.size),
            "active_cell_count": int(session.active_cell_count),
            "cumulative_cell_updates": int(session.cell_steps),
            "worker_count": session.worker_count,
            "rain_m3": float(session.rain_m3),
            "drain_m3": float(session.drain_m3),
            "boundary_outflow_m3": float(session.boundary_outflow_m3),
            "water_m3": water,
            "mass_error_m3": error,
        }
        np.save(directory / f"{stem}.npy", session.depth.reshape(self.grid.valid.shape).astype(np.float32))
        (directory / f"{stem}.png").write_bytes(self.rasters.depth_png(session.depth))
        row = {"frame_source": "computed", **frame, "active_tiles": [self.tiles.ids[i] for i in session.active_tiles]}
        # Metadata is the completion marker for the three files.
        marker = directory / f"{stem}.tmp"
        marker.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
        marker.replace(directory / f"{stem}.json")
        with self.condition:
            self.frames.append(frame)

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
        depth = np.load(directory / f"{stem}.npy", mmap_mode="r")
        cells = self.tiles.members[index]
        values = depth.ravel()[cells]
        tile_id = self.tiles.ids[index]
        gauge_indices = self.gauge_map.ravel()[cells]
        if row is not None:
            gauge_indices = [self.gauge_map[row, col]]
        return {
            "tile_id": tile_id,
            "active": tile_id in meta["active_tiles"],
            "time": meta["time"],
            "depth_m": float(depth[row, col]) if row is not None else None,
            "min_tile_depth_m": float(values.min()),
            "max_tile_depth_m": float(values.max()),
            "rain": [
                {"station_id": self.gauges[i][0], "name": self.gauges[i][3], "mm": meta["rain_interval_mm"][i]}
                for i in np.unique(gauge_indices)
            ],
        }
