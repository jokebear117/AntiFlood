"""Render computed depth and FABDEM elevation in Web Mercator."""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.features import shapes
from rasterio.transform import array_bounds, from_bounds
from rasterio.warp import reproject, transform_bounds, transform_geom

from .data import CELL_M, DEFAULT_BOUNDS, MAX_GAUGE_DISTANCE_M, SEOUL_CRS, read_elevation

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
# Effective drainage: -1 marks cells that use the assumed rate.
DRAIN_BINS = (0, 40, 55, 70, 78)
DRAIN_COLORS = (
    (0, 0, 0, 0),
    (150, 150, 150, 120),
    (214, 76, 52, 170),
    (240, 150, 70, 160),
    (246, 210, 110, 150),
    (120, 190, 160, 140),
    (60, 140, 175, 140),
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
        self.domain = None
        if grid.wgs_bounds == DEFAULT_BOUNDS:
            mask = grid.valid.astype(np.uint8)
            polygons = [
                geometry["coordinates"]
                for geometry, _ in shapes(mask, mask=grid.valid, transform=grid.affine)
            ]
            self.domain = transform_geom(
                SEOUL_CRS, "EPSG:4326", {"type": "MultiPolygon", "coordinates": polygons}, precision=6,
            )

    def depth_png(self, depth):
        return array_png(depth.reshape(self.grid.valid.shape), self.grid.valid, self.grid.affine)

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
            "domain": self.domain,
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
            "drainage": self.grid.drainage_summary,
            "drainage_legend": [{"min_mm_h": bound, "rgb": color[:3]} for bound, color in zip(DRAIN_BINS, DRAIN_COLORS[2:])],
            "valid_cell_count": int(self.grid.valid.sum()),
            "max_gauge_distance_m": MAX_GAUGE_DISTANCE_M,
            "boundary": self.grid.boundary_mode,
        }


def array_png(values, valid, affine, layer="depth"):
    height, width = valid.shape
    bounds = transform_bounds(SEOUL_CRS, MERCATOR, *array_bounds(height, width, affine))
    destination = from_bounds(*bounds, width, height)
    nodata = -9999
    warped = np.full(valid.shape, nodata, dtype=np.float32)
    reproject(
        np.where(valid, values.astype(np.float32, copy=False), nodata), warped,
        src_transform=affine, src_crs=SEOUL_CRS,
        dst_transform=destination, dst_crs=MERCATOR, src_nodata=nodata, dst_nodata=nodata,
        resampling=Resampling.nearest,
    )
    if layer == "active":
        colors = [(0, 0, 0, 0), (140, 155, 168, 100), (246, 194, 74, 180), (224, 102, 36, 210), (180, 54, 38, 230), (30, 137, 210, 225)]
        indices = np.digitize(warped, (-0.5, 0.5, 1.5, 2.5, 3.5))
    elif layer == "difference":
        colors = [(0, 0, 0, 0), (22, 79, 177, 235), (85, 164, 213, 205),
                  (0, 0, 0, 0), (244, 152, 81, 205), (184, 58, 27, 235)]
        indices = np.digitize(warped, (-1, -0.05, -0.001, 0.001, 0.05))
        indices[(warped < -1) & (warped != nodata)] = 1
    elif layer == "drainage":
        colors = DRAIN_COLORS
        indices = np.digitize(warped, (-1.5, -0.5, *DRAIN_BINS[1:]))
        indices[warped == nodata] = 0
    else:
        colors = DEPTH_COLORS
        indices = np.digitize(warped, DEPTH_BINS)
    return png(np.asarray(colors, dtype=np.uint8)[indices])
