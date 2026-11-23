"""Render computed depth and FABDEM elevation in Web Mercator."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import array_bounds, from_bounds
from rasterio.warp import reproject, transform_bounds

from .data import CELL_M, MAX_GAUGE_DISTANCE_M, SEOUL_CRS, read_elevation

MERCATOR = "EPSG:3857"
WORLD_EDGE = 20037508.342789244
TILE_PIXELS = 256
DEPTH_BINS = (0.001, 0.05, 0.15, 0.30)
DEPTH_COLORS = (
    (0, 0, 0, 0),
    (88, 199, 237, 205),
    (30, 137, 210, 225),
    (40, 78, 180, 240),
    (115, 47, 152, 245),
)
FABDEM = "FABDEM V1-2 © University of Bristol and Fathom (CC BY-NC-SA 4.0)"


def png(array):
    buffer = BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


class MapRasters:
    def __init__(self, grid, dataset: Path):
        self.grid = grid
        self.height, self.width = grid.valid.shape
        bounds = transform_bounds(
            SEOUL_CRS, MERCATOR, *array_bounds(self.height, self.width, grid.affine)
        )
        self.overlay_affine = from_bounds(*bounds, self.width * 2, self.height * 2)
        west, south, east, north = transform_bounds(MERCATOR, "EPSG:4326", *bounds)
        self.corners = [[west, north], [east, north], [east, south], [west, south]]
        self.dataset = dataset

    def depth_png(self, depth):
        depth = np.where(self.grid.valid, depth.reshape(self.grid.valid.shape), -1)
        warped = np.full((self.height * 2, self.width * 2), -1.0, dtype=np.float32)
        reproject(
            depth, warped, src_transform=self.grid.affine, src_crs=SEOUL_CRS,
            dst_transform=self.overlay_affine, dst_crs=MERCATOR,
            src_nodata=-1, dst_nodata=-1, resampling=Resampling.nearest,
        )
        return png(np.asarray(DEPTH_COLORS, dtype=np.uint8)[np.digitize(warped, DEPTH_BINS)])

    @lru_cache(maxsize=384)
    def terrain_png(self, zoom, x, y):
        tile_m = 2 * WORLD_EDGE / (2 ** zoom)
        left = -WORLD_EDGE + x * tile_m
        top = WORLD_EDGE - y * tile_m
        affine = from_bounds(left, top - tile_m, left + tile_m, top, TILE_PIXELS, TILE_PIXELS)
        elevation = np.full((TILE_PIXELS, TILE_PIXELS), np.nan, dtype=np.float32)
        read_elevation(self.dataset, elevation, affine, MERCATOR)
        elevation = np.nan_to_num(elevation, nan=0)
        code = np.rint((elevation + 32768) * 256).clip(0, 2**24 - 1).astype(np.uint32)
        return png(np.stack((code >> 16, code >> 8, code), axis=-1).astype(np.uint8))

    def metadata(self):
        return {
            "bounds": self.grid.wgs_bounds,
            "frame_coordinates": self.corners,
            "grid_crs": str(SEOUL_CRS),
            "grid_transform": tuple(self.grid.affine)[:6],
            "grid_shape": self.grid.valid.shape,
            "cell_m": CELL_M,
            "tile_m": 100,
            "legend": [{"min_m": bound, "rgb": color[:3]} for bound, color in zip(DEPTH_BINS, DEPTH_COLORS[1:])],
            "terrain_attribution": FABDEM,
            "drainage_source": self.grid.drainage_source,
            "drainage_raster_source": self.grid.drainage_raster_source,
            "drainage_fallback_cells": self.grid.drainage_fallback_cells,
            "default_drain_mm_h": self.grid.default_drain_mm_h,
            "valid_cell_count": int(self.grid.valid.sum()),
            "max_gauge_distance_m": MAX_GAUGE_DISTANCE_M,
            "boundary": self.grid.boundary_mode,
        }
