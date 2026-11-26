"""Match completed runs and compare their numerical depth arrays."""

from dataclasses import asdict
from hashlib import sha256
import json
import os
import platform
from pathlib import Path
from contextlib import closing

import numpy as np

from .data import CELL_M, utc
from .stream import RISK

FLOOD_THRESHOLD_M = 0.05


def run_conditions(grid, gauge_map, scenario, threads, engine):
    digest = sha256()
    for array in (grid.valid, grid.elevation, grid.boundary_elevation, grid.drain, gauge_map):
        digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
    with closing(scenario.iter_intervals()) as intervals:
        for interval in intervals:
            digest.update(utc(interval.start).encode())
            digest.update(utc(interval.end).encode())
            digest.update(memoryview(interval.gauge_mm).cast("B"))
            del interval
    environment = {
        "host": platform.node(),
        "os": platform.platform(),
        "cpu": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "engine_sha256": sha256(Path(engine.library._name).read_bytes()).hexdigest(),
    }
    return {
        "input_sha256": digest.hexdigest(),
        "bounds": list(grid.wgs_bounds),
        "grid_transform": list(grid.affine)[:6],
        "grid_shape": list(grid.valid.shape),
        "scenario": scenario.summary(),
        "boundary": grid.boundary_mode,
        "initial_depth_m": 0,
        "cell_m": CELL_M,
        "manning": 0.04,
        "max_step_seconds": 15,
        "threads": threads,
        "risk": asdict(RISK),
        "environment": environment,
    }


def reusable_reference(root, conditions):
    for path in sorted(root.glob("*/run.json"), reverse=True):
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (info.get("mode"), info.get("status"), info.get("conditions")) != ("reference", "completed", conditions):
            continue
        count = conditions["scenario"]["interval_count"]
        if all(
            (path.parent / f"{i:05d}.json").is_file() and (path.parent / f"{i:05d}.npz").is_file()
            for i in range(count)
        ) and (path.parent / "maximum.npz").is_file():
            return path.parent
    return None


def accuracy(reference, streaming, valid):
    ref = reference[valid]
    stream = streaming[valid]
    squared = np.square(stream - ref, dtype=np.float64)
    ref_flood = ref >= FLOOD_THRESHOLD_M
    stream_flood = stream >= FLOOD_THRESHOLD_M
    union = ref_flood | stream_flood
    return {
        "threshold_m": FLOOD_THRESHOLD_M,
        "rmse_m": float(np.sqrt(squared.mean())),
        "flood_rmse_m": float(np.sqrt(squared[union].mean())) if union.any() else None,
        "iou": float((ref_flood & stream_flood).sum() / union.sum()) if union.any() else None,
    }


def performance(reference, streaming):
    ref_seconds = reference["calculation_seconds"]
    stream_seconds = streaming["calculation_seconds"]
    ref_cells = reference["cumulative_cell_updates"]
    stream_cells = streaming["cumulative_cell_updates"]
    return {
        "speedup": ref_seconds / stream_seconds if stream_seconds else None,
        "time_reduction": 1 - stream_seconds / ref_seconds if ref_seconds else None,
        "cell_reduction": 1 - stream_cells / ref_cells if ref_cells else None,
    }
