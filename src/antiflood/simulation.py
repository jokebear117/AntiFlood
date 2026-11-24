"""Keep one continuous depth grid and advance it with the native WCA2D kernel."""

import ctypes
from datetime import timedelta
import os
from pathlib import Path
import shutil
import sys

import numpy as np
from numpy.ctypeslib import ndpointer

from .data import CELL_M, ROOT
from .stream import RainHistory
from .tiles import HALO, TileGrid


class NativeEngine:
    def __init__(self):
        extension = {"win32": "dll", "darwin": "dylib"}.get(sys.platform, "so")
        directory = "engine" if sys.platform == "win32" else "engine-linux"
        default = ROOT / f"build/{directory}/antiflood_engine.{extension}"
        library = Path(os.getenv("ANTIFLOOD_ENGINE", default)).resolve()
        if not library.is_file():
            raise FileNotFoundError(f"계산 엔진을 찾을 수 없습니다. README의 빌드 명령을 실행해 주세요. ({library.name})")
        dll_dir = None
        if sys.platform == "win32":
            gcc = shutil.which("g++")
            runtime = os.getenv("ANTIFLOOD_DLL_DIR", str(Path(gcc).parent) if gcc else "")
            if runtime:
                dll_dir = os.add_dll_directory(runtime)
        try:
            self.library = ctypes.CDLL(str(library))
        finally:
            if dll_dir:
                dll_dir.close()
        self.step = self.library.wca_selective_step
        f64 = ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
        i32 = ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
        u8 = ndpointer(dtype=np.uint8, flags="C_CONTIGUOUS")
        self.step.argtypes = [
            f64, f64, f64, f64, f64, i32, i32, ctypes.c_int, i32, u8, ctypes.c_int,
            ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int, f64, f64, u8,
        ]
        self.step.restype = ctypes.c_int


class SimulationSession:
    def __init__(self, grid, tiles: TileGrid, engine, gauge_map, gauge_count, start, threads, mode="streaming"):
        self.grid = grid
        self.tiles = tiles
        self.engine = engine
        self.gauge_map = gauge_map.ravel()
        self.history = RainHistory(gauge_count)
        self.depth = np.zeros(grid.valid.size)
        self.maximum_depth = np.zeros_like(self.depth)
        self.rain = np.zeros_like(self.depth)
        self.outflow = np.empty((self.depth.size, 4))
        self.budget = np.zeros(3)
        self.rain_m3 = self.drain_m3 = self.boundary_outflow_m3 = 0.0
        self.threads = threads
        self.worker_count = self.cell_steps = self.active_cell_count = 0
        self.active_tiles = np.empty(0, dtype=np.int32)
        self.mode = mode
        self.received = np.zeros(self.depth.size, dtype=np.uint8)
        self.selected = np.ascontiguousarray(tiles.valid, dtype=np.uint8)
        self.last_update = np.full(len(tiles.ids), -1.0)
        self.elapsed = 0.0
        self.time = start
        self.interval = None
        self.remaining = 0.0
        self.manning = 0.04

    def set_rain(self, interval):
        if interval.start != self.time or self.remaining > 0:
            raise ValueError("강우 구간이 현재 계산 시각과 이어지지 않습니다.")
        self.interval = interval
        self.remaining = (interval.end - interval.start).total_seconds()
        cells = self.tiles.cells
        region = self.gauge_map[cells]
        self.rain[cells] = interval.gauge_mm[region] / (1_000 * self.remaining)
        if self.mode == "streaming":
            self.history.add(interval.gauge_mm)
            self.tile_rain = self.tiles.rain_state(self.gauge_map, interval.gauge_mm, self.history)
        self.max_rain_rate = self.rain.max()

    def advance_step(self):
        if not self.remaining:
            raise ValueError("계산할 강우 구간이 없습니다.")
        valid = self.tiles.cells
        if self.mode == "streaming":
            self.tile_modes, self.tile_reasons = self.tiles.select(self.depth, self.tile_rain, self.received)
            active = self.tile_modes >= HALO
            self.active_tiles = np.flatnonzero(active)
            self.selected[valid] = active[self.tiles.valid_tiles]
            cells = valid[self.selected[valid] != 0]
        else:
            self.active_tiles = np.arange(len(self.tiles.ids))
            cells = valid
        self.active_cell_count = cells.size
        self.cell_steps += cells.size
        # Both policies use the full grid for the same CFL bound.
        max_depth = self.depth.max() + self.max_rain_rate * 15
        speed = min(10.0, 3.132 * np.sqrt(max_depth))
        dt = min(self.remaining, 15.0, 0.5 * CELL_M / max(speed, 1.0))
        team = self.engine.step(
            self.grid.elevation, self.grid.boundary_elevation, self.depth, self.rain, self.grid.drain,
            self.tiles.neighbours, valid, valid.size, cells, self.selected, cells.size,
            CELL_M, dt, self.manning, self.threads, self.outflow, self.budget, self.received,
        )
        self.worker_count = max(team, self.worker_count)
        self.rain_m3 += self.budget[0]
        self.drain_m3 += self.budget[1]
        self.boundary_outflow_m3 += self.budget[2]
        np.maximum(self.maximum_depth, self.depth, out=self.maximum_depth)
        self.elapsed += dt
        self.last_update[self.active_tiles] = self.elapsed
        self.remaining = max(0.0, self.remaining - dt)
        self.time = self.interval.end - timedelta(seconds=self.remaining)
        return self.remaining == 0

    def verify(self):
        total = self.depth.sum() * CELL_M ** 2
        error = total - (self.rain_m3 - self.drain_m3 - self.boundary_outflow_m3)
        tolerance = max(1e-7, self.rain_m3 * 1e-10)
        if not np.isfinite(total) or self.depth.min() < 0 or abs(error) > tolerance:
            raise RuntimeError(f"수량 또는 수심 검증에 실패했습니다. (수량 오차 {error:.6g} m³)")
        return float(total), float(error)
