"""Map cell centres to metric 100 m tiles and select cells before each physical step."""

import numpy as np
from .data import CELL_M


class TileGrid:
    def __init__(self, grid):
        rows, cols = np.indices(grid.valid.shape)
        x = np.floor((grid.affine.c + (cols + 0.5) * CELL_M) / 100).astype(np.int32)
        y = np.floor((grid.affine.f - (rows + 0.5) * CELL_M) / 100).astype(np.int32)
        self.valid = grid.valid.ravel()
        self.cells = np.flatnonzero(self.valid)
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
        self.members = tuple(np.split(
            self.cells[np.argsort(cell_tiles.ravel(), kind="stable")],
            np.cumsum(np.bincount(cell_tiles.ravel(), minlength=len(pairs)))[:-1],
        ))

    def prepare(self, rain, scores, depth):
        tile_score = np.full(len(self.ids), -np.inf)
        np.maximum.at(tile_score, self.valid_tiles, scores[self.cells])
        residual = np.zeros(len(self.ids))
        np.maximum.at(residual, self.valid_tiles, depth[self.cells])
        raining = np.zeros(len(self.ids), dtype=bool)
        raining[self.by_cell[np.flatnonzero(rain > 0)]] = True
        tile_order = np.argsort(-(tile_score + np.minimum(residual, 1) * 10), kind="stable")
        cell_order = np.concatenate([self.members[i] for i in tile_order]).astype(np.int32)
        return raining, tile_order, cell_order

    def select(self, depth, raining, tile_order, cell_order):
        donors = raining.copy()
        donors[self.valid_tiles[depth[self.cells] > 0]] = True
        halo = self.tile_neighbours[donors].ravel()
        included = donors.copy()
        included[halo[halo >= 0]] = True
        ordered = tile_order[included[tile_order]]
        active = cell_order[included[self.by_cell[cell_order]]]
        selected = np.ascontiguousarray(included[self.by_cell] & self.valid, dtype=np.uint8)
        return ordered, active, selected
