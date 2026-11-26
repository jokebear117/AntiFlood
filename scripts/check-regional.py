"""Native regional-clock safety checks; no server or existing results are changed.

Run from the repository root: python scripts/check-regional.py
Use ANTIFLOOD_ENGINE for a separate build. Reports errors without defining an
acceptance threshold for Reference agreement. This is not a Seoul benchmark.
"""

from datetime import datetime, timedelta, timezone
import json
from time import perf_counter, process_time
from types import SimpleNamespace

from affine import Affine
import numpy as np

from antiflood.simulation import NativeEngine, SimulationSession
from antiflood.tiles import TileGrid


def check_decay(engine):
    shape = (1, 180)
    grid = SimpleNamespace(valid=np.ones(shape, dtype=bool), affine=Affine(30, 0, 0, 0, -30, 200),
                           elevation=np.zeros(180), drain=np.zeros(180),
                           boundary_elevation=np.full((180, 4), np.nan))
    tiles = TileGrid(grid)
    gauges = np.zeros(shape, dtype=np.int32)
    gauges[:, :3] = 1
    start = datetime(2022, 8, 8, tzinfo=timezone.utc)
    s = SimulationSession(grid, tiles, engine, gauges, 2, start, 4, "streaming")
    s.history.decay_mm[1] = 40
    s.set_rain(SimpleNamespace(start=start, end=start + timedelta(seconds=600), gauge_mm=np.zeros(2)))
    while not s.advance_step():
        s.verify()
    assert s.verify() == (0., 0.)
    assert set(np.unique(s.tile_step_seconds)) == {15., 60.}
    assert np.all(s.last_update == 600)
    return {"decay_only_shortens_period": True, "zero_water_preserved": True,
            "tile_periods_seconds": np.unique(s.tile_step_seconds).tolist()}


def check_subthreshold(engine, horizon=60.):
    """Shallow wet cells advance exactly until the native outflow cutoff."""
    shape = (3, 180)
    grid = SimpleNamespace(valid=np.ones(shape, dtype=bool), affine=Affine(30, 0, 0, 0, -30, 200),
                           elevation=np.tile(np.linspace(.2, 0, 180), (3, 1)).ravel(),
                           drain=np.full(540, .2 / 3_600_000),
                           boundary_elevation=np.full((540, 4), np.nan))
    grid.boundary_elevation[180, 2] = -.1
    tiles = TileGrid(grid)
    start = datetime(2022, 8, 8, tzinfo=timezone.utc)
    sessions = [SimulationSession(grid, tiles, engine, np.zeros(shape, dtype=np.int32),
                                  1, start, 4, mode) for mode in ("reference", "streaming")]
    sessions[1].synchronization_seconds = horizon
    frames = []
    for index, rain in enumerate((.6, 0., .6)):
        interval = SimpleNamespace(start=start + timedelta(seconds=index * 600),
                                   end=start + timedelta(seconds=(index + 1) * 600),
                                   gauge_mm=np.array([rain]))
        wet_coarse = 0
        for s in sessions:
            s.set_rain(interval)
            while True:
                done = s.advance_step()
                s.verify()
                assert np.isfinite(s.depth).all() and np.isfinite(s.maximum_depth).all()
                assert np.all(s.maximum_depth >= s.depth)
                if s.mode == "streaming" and s._slab_remaining == 0:
                    np.testing.assert_allclose(s.last_update, s.elapsed, rtol=0, atol=1e-8)
                    wet_coarse += int(np.count_nonzero(s.depth[s._slow_cells]))
                    assert not np.any(s.outflow[s._slow_cells])
                if done:
                    break
            assert s.time == interval.end
        ref, stream = sessions
        if index < 2:
            # Both are integrating the same constant-source no-flow ODE.
            np.testing.assert_allclose(stream.depth, ref.depth, rtol=0, atol=1e-17)
            np.testing.assert_allclose(stream.maximum_depth, ref.maximum_depth, rtol=0, atol=1e-17)
            assert wet_coarse > 0 and np.all(stream.tile_step_seconds == horizon)
            assert stream.boundary_outflow_m3 == 0
        else:
            assert stream.boundary_outflow_m3 > 0
            assert np.any(stream.tile_step_seconds <= 15)
        frames.append({"time": stream.time.isoformat(), "rain_mm": rain,
                       "rmse_m": float(np.sqrt(np.mean((ref.depth - stream.depth) ** 2))),
                       "mass_error_m3": stream.verify()[1], "wet_coarse_cell_observations": wet_coarse,
                       "boundary_outflow_m3": stream.boundary_outflow_m3,
                       "tile_periods_seconds": np.unique(stream.tile_step_seconds).tolist(),
                       "cell_updates": {s.mode: int(s.cell_steps) for s in sessions}})
    assert stream.cell_steps < ref.cell_steps
    return {"horizon_seconds": horizon, "frames": frames,
            "workers": {s.mode: s.worker_count for s in sessions}, "requested_threads": 4,
            "scope": "Synthetic slope with real native cutoff; no performance or Seoul claim"}


def check_cutoff(engine):
    # Disconnected cells in different tiles: spatial no-data must not connect
    # their dependency cones. Exactly 1 mm must use the fine clock, since the
    # native cutoff is strictly less than 0.001 m, not less-than-or-equal.
    valid = np.zeros((1, 11), dtype=bool)
    valid[0, [0, 5, 10]] = True
    grid = SimpleNamespace(valid=valid, affine=Affine(30, 0, 0, 0, -30, 200),
                           elevation=np.zeros(11), drain=np.zeros(11),
                           boundary_elevation=np.full((11, 4), np.nan))
    grid.boundary_elevation[[0, 5, 10], 0] = -.1
    gauges = np.zeros(valid.shape, dtype=np.int32)
    gauges[0, [0, 5, 10]] = [0, 1, 2]
    tiles = TileGrid(grid)
    start = datetime(2022, 8, 8, tzinfo=timezone.utc)
    s = SimulationSession(grid, tiles, engine, gauges, 3, start, 4, "streaming")
    s.set_rain(SimpleNamespace(start=start, end=start + timedelta(seconds=60),
                               gauge_mm=np.array([np.nextafter(1., 0.), 1., np.nextafter(1., 2.)])))
    while not s.advance_step():
        s.verify()
    s.verify()
    assert s.tile_step_seconds[tiles.by_cell[0]] == 60
    assert np.all(s.tile_step_seconds[tiles.by_cell[[5, 10]]] == 15)
    assert not np.any(s.outflow[0]) and np.any(s.outflow[[5, 10]])
    assert np.all(s.last_update == 60)
    return {"strict_cutoff_and_nodata": True, "mass_error_m3": s.verify()[1],
            "periods_below_at_above_seconds": s.tile_step_seconds[tiles.by_cell[[0, 5, 10]]].tolist()}


def check(engine, horizon, boundary, amount):
    shape = (3, 180)
    valid = np.ones(shape, dtype=bool)
    valid[0, 0] = False
    grid = SimpleNamespace(
        valid=valid, affine=Affine(30, 0, 0, 0, -30, 200),
        elevation=np.tile(np.linspace(.2, 0, shape[1]), (shape[0], 1)).ravel(),
        drain=np.full(valid.size, .5 / 3_600_000),
        boundary_elevation=np.full((valid.size, 4), np.nan),
    )
    if boundary == "open":
        grid.boundary_elevation[shape[1], 2] = -.1
    tiles = TileGrid(grid)
    gauges = np.zeros(shape, dtype=np.int32)
    gauges[:, :3] = 1
    gauges[:, -3:] = 2
    start = datetime(2022, 8, 8, tzinfo=timezone.utc)
    sessions = [SimulationSession(grid, tiles, engine, gauges, 3, start, 4, mode)
                for mode in ("reference", "streaming")]
    sessions[1].synchronization_seconds = horizon
    seconds = {s.mode: 0.0 for s in sessions}
    cpu = dict(seconds)
    frames = []
    initially_deferred = None
    interface_checks = 0
    for index, rain in enumerate(([0., amount, 0.], [0., 0., 0.], [0., 0., amount])):
        interval = SimpleNamespace(start=start + timedelta(seconds=index * 600),
                                   end=start + timedelta(seconds=(index + 1) * 600),
                                   gauge_mm=np.array(rain))
        for s in sessions:
            s.set_rain(interval)
            wall, used = perf_counter(), process_time()
            while True:
                done = s.advance_step()
                if s.mode == "streaming":
                    if initially_deferred is None:
                        initially_deferred = s._slow_cells.copy()
                    # No volume may cross the certified coarse/fine cut during
                    # a slab. Once a front approaches, the next slab must move
                    # those tiles to the short clock before they receive flow.
                    adjacent = tiles.neighbours[s._fast_cells]
                    slow = np.zeros(valid.size, dtype=bool)
                    slow[s._slow_cells] = True
                    cut = (adjacent >= 0) & slow[np.maximum(adjacent, 0)]
                    assert not np.any(s.outflow[s._fast_cells][cut])
                    interface_checks += 1
                s.verify()
                assert np.isfinite(s.depth).all() and np.isfinite(s.maximum_depth).all()
                assert (s.depth >= 0).all() and (s.maximum_depth >= s.depth).all()
                if s.mode == "streaming" and s._slab_remaining == 0:
                    np.testing.assert_allclose(s.last_update, s.elapsed, rtol=0, atol=1e-8)
                if done:
                    break
            seconds[s.mode] += perf_counter() - wall
            cpu[s.mode] += process_time() - used
            assert s.time == interval.end
            np.testing.assert_allclose(s.last_update, s.elapsed, rtol=0, atol=1e-8)
        ref, stream = sessions
        flooded = (ref.depth >= .05) | (stream.depth >= .05)
        frames.append({
            "time": stream.time.isoformat(),
            "rmse_m": float(np.sqrt(np.mean((ref.depth - stream.depth) ** 2))),
            "max_abs_difference_m": float(np.max(np.abs(ref.depth - stream.depth))),
            "iou_005m": float(np.sum((ref.depth >= .05) & (stream.depth >= .05)) / flooded.sum())
                        if flooded.any() else None,
            "mass_error_m3": stream.verify()[1],
            "water_m3": stream.verify()[0],
            "boundary_outflow_m3": stream.boundary_outflow_m3,
            "tile_periods_seconds": np.unique(stream.tile_step_seconds).tolist(),
            "cell_updates": {s.mode: int(s.cell_steps) for s in sessions},
        })
    assert stream.cell_steps < ref.cell_steps, "No actual cell operation reduction"
    assert any(horizon in frame["tile_periods_seconds"] for frame in frames), frames
    assert any(min(frame["tile_periods_seconds"]) <= 15 for frame in frames)
    assert stream.drain_m3 > 0
    assert stream.boundary_outflow_m3 > 0 if boundary == "open" else stream.boundary_outflow_m3 == 0
    newly_wet = int(np.count_nonzero(stream.depth[initially_deferred]))
    rain_free_deferred = initially_deferred[gauges.ravel()[initially_deferred] == 0]
    front_wet = int(np.count_nonzero(stream.depth[rain_free_deferred]))
    if amount == 600:
        assert front_wet > 0, "A front never reached a formerly deferred rain-free tile"
    return {"horizon_seconds": horizon, "boundary": boundary, "rain_mm": amount,
            "zero_cross_clock_flux_checks": interface_checks,
            "formerly_deferred_cells_now_wet": newly_wet,
            "formerly_deferred_rain_free_cells_now_wet": front_wet,
            "cells": int(valid.sum()), "requested_threads": 4,
            "workers": {s.mode: s.worker_count for s in sessions},
            "checked_loop_wall_seconds": seconds, "checked_loop_cpu_seconds": cpu,
            "timing_scope": "Includes per-step assertions and mass checks; not a physics benchmark",
            "frames": frames}


if __name__ == "__main__":
    engine = NativeEngine()
    print(json.dumps({"decay": check_decay(engine),
                      "cutoff": check_cutoff(engine),
                      "subthreshold": [check_subthreshold(engine, h) for h in (30., 60.)],
                      "checks": [check(engine, horizon, boundary, amount)
                                  for horizon, boundary, amount in
                                  ((30., "closed", 2.), (60., "open", 2.), (60., "closed", 600.))]},
                     indent=2))
