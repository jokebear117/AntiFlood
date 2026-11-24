"""Map cell centres to metric 100 m tiles and select cells before each physical step."""

import numpy as np
from .data import CELL_M
from .stream import RISK

DRY, LOW, HALO, HIGH = range(4)
# KEPT: already active earlier in the same 10-minute interval (set by the simulation session).
RAIN, SLIDING, DECAY, DEPTH, NEIGHBOUR, INFLOW, KEPT = (1 << bit for bit in range(7))


class TileGrid:
    def __init__(self, grid):
        rows, cols = np.indices(grid.valid.shape)
        x = np.floor((grid.affine.c + (cols + 0.5) * CELL_M) / 100).astype(np.int32)
        y = np.floor((grid.affine.f - (rows + 0.5) * CELL_M) / 100).astype(np.int32)
        self.valid = grid.valid.ravel()
        self.cells = np.flatnonzero(self.valid).astype(np.int32)
        pairs, cell_tiles = np.unique(np.column_stack((x.ravel()[self.cells], y.ravel()[self.cells])),
                                      axis=0, return_inverse=True)
        self.ids = tuple(f"{tx}_{ty}" for tx, ty in pairs)
        self.lookup = {tile_id: index for index, tile_id in enumerate(self.ids)}
        self.by_cell = np.full(self.valid.size, -1, dtype=np.int32)
        self.by_cell[self.cells] = cell_tiles.ravel()
        self.valid_tiles = self.by_cell[self.cells]

        flat = np.arange(self.valid.size, dtype=np.int32).reshape(grid.valid.shape)
        padded = np.pad(np.where(grid.valid, flat, -1), 1, constant_values=-1)
        self.neighbours = np.ascontiguousarray(np.stack((
            padded[1:-1, 2:], padded[:-2, 1:-1], padded[1:-1, :-2], padded[2:, 1:-1],
        ), axis=-1).reshape(-1, 4), dtype=np.int32)
        self.tile_neighbours = np.full((len(pairs), 4), -1, dtype=np.int32)
        by_pair = {tuple(pair): index for index, pair in enumerate(pairs)}
        for index, (tx, ty) in enumerate(pairs):
            for k, offset in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
                self.tile_neighbours[index, k] = by_pair.get((tx + offset[0], ty + offset[1]), -1)
        self.ordered_cells = self.cells[np.argsort(self.valid_tiles, kind="stable")]
        self.starts = np.r_[0, np.cumsum(np.bincount(self.valid_tiles))[:-1]]
        self.members = tuple(np.split(self.ordered_cells, self.starts[1:]))
        self.padded_tile_neighbours = np.where(self.tile_neighbours < 0, len(pairs), self.tile_neighbours)

    def maximum(self, values):
        return np.maximum.reduceat(values[self.ordered_cells], self.starts)

    def rain_state(self, gauge_map, rain, history):
        gauges = gauge_map[self.ordered_cells]
        return np.stack([
            np.maximum.reduceat(values[gauges], self.starts)
            for values in (rain, history.hour_mm, history.decay_mm)
        ])

    def select(self, depth, rainfall, received):
        rain, sliding, decay = rainfall
        maximum = self.maximum(depth)
        reasons = np.asarray(
            RAIN * (rain >= RISK.rain_mm)
            + SLIDING * (sliding >= RISK.hour_mm)
            + DECAY * (decay >= RISK.decay_mm)
            + DEPTH * (maximum >= RISK.depth_m), dtype=np.uint8,
        )
        high = reasons != 0
        adjacent = np.r_[high, False][self.padded_tile_neighbours].any(axis=1)
        incoming = self.maximum(received) != 0
        reasons[~high & adjacent] |= NEIGHBOUR
        reasons[~high & incoming] |= INFLOW
        modes = np.full(len(self.ids), DRY, dtype=np.uint8)
        modes[(rain > 0) | (maximum > 0)] = LOW
        modes[adjacent | incoming] = HALO
        modes[high] = HIGH
        return modes, reasons
