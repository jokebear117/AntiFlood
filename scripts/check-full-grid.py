"""Small native checks for the full-grid synchronous baseline; no server writes.

Run from the repository root with the prepared Python environment:
    python scripts/check-full-grid.py
ANTIFLOOD_ENGINE may point to a separate build to preserve the serving library.
These checks do not validate regional time stepping or benchmark performance.
The adaptive session uses a 15-second synchronization horizon to recover the
shared clock on this shallow fixture. check-regional.py covers longer clocks.
"""

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import numpy as np
from affine import Affine

from antiflood.simulation import NativeEngine, SimulationSession
from antiflood.tiles import FULL_GRID, TileGrid


def check(engine, boundary):
    shape = (5, 8)
    valid = np.ones(shape, dtype=bool)
    valid[0, 0] = False  # An internal no-data edge must remain sealed.
    elevation = np.tile(np.linspace(0.3, 0, shape[1]), (shape[0], 1)).ravel()
    grid = SimpleNamespace(valid=valid, elevation=elevation,
                           affine=Affine(30, 0, 0, 0, -30, 200),
                           drain=np.full(valid.size, 0.5 / 3_600_000),
                           boundary_elevation=np.full((valid.size, 4), np.nan))
    tiles = TileGrid(grid)
    if boundary == "open":
        # Open one rainy exterior edge; the remaining exterior/no-data is sealed.
        grid.boundary_elevation[shape[1], 2] = -0.1
    gauges = np.zeros(shape, dtype=np.int32)
    gauges[:, :4] = 1
    start = datetime(2022, 8, 8, tzinfo=timezone.utc)
    sessions = [SimulationSession(grid, tiles, engine, gauges, 2, start, 4, mode)
                for mode in ("reference", "streaming")]
    sessions[1].synchronization_seconds = 15.0
    snapshots = []
    initial_wet = None
    for index, amounts in enumerate(([0.0, 2.0], [0.0, 0.0], [0.0, 0.0])):
        interval = SimpleNamespace(start=start + timedelta(seconds=600 * index),
                                   end=start + timedelta(seconds=600 * (index + 1)),
                                   gauge_mm=np.array(amounts, dtype=np.float64))
        for session in sessions:
            session.set_rain(interval)
            while True:
                done = session.advance_step()
                session.verify()
                assert np.isfinite(session.depth).all()
                assert np.isfinite(session.maximum_depth).all()
                assert (session.depth >= 0).all()
                assert (session.maximum_depth >= session.depth).all()
                assert session.active_cell_count == valid.sum()
                assert np.all(session.last_update == session.elapsed)
                assert session.time <= interval.end
                if done:
                    break
            assert session.time == interval.end
        reference, streaming = sessions
        np.testing.assert_array_equal(reference.depth, streaming.depth)
        np.testing.assert_array_equal(reference.maximum_depth, streaming.maximum_depth)
        assert reference.cell_steps == streaming.cell_steps
        assert np.all(streaming.tile_modes == FULL_GRID)
        assert reference.depth[0] == 0
        if index == 0:
            initial_wet = streaming.depth.copy()
        snapshots.append({"time": streaming.time.isoformat(),
                          "cell_updates": streaming.cell_steps,
                          "water_m3": streaming.verify()[0],
                          "mass_error_m3": streaming.verify()[1],
                          "boundary_outflow_m3": streaming.boundary_outflow_m3,
                          "worker_count": streaming.worker_count,
                          "rmse_m": 0.0})
    assert (streaming.depth.reshape(shape)[:, 4:] > 0).any(), "No transfer into rain-free tiles"
    assert not np.array_equal(initial_wet, streaming.depth), "Water stopped moving after rain"
    assert streaming.drain_m3 > 0
    if boundary == "closed":
        assert streaming.boundary_outflow_m3 == 0
    else:
        assert streaming.boundary_outflow_m3 > 0
    return {"boundary": boundary, "valid_cells": int(valid.sum()), "frames": snapshots}


if __name__ == "__main__":
    engine = NativeEngine()
    print(json.dumps({"engine": str(engine.library._name),
                      "checks": [check(engine, boundary) for boundary in ("closed", "open")]},
                     indent=2))
