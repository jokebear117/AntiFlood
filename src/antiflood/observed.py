"""Read Seoul's August 8–9 flood footprints and compare their overlap on the model grid."""

from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
import re
from zipfile import ZipFile

import numpy as np
import shapefile
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_bounds, transform_geom

OBSERVED_SOURCE = "서울시 침수흔적도 OA-15636"
OBSERVED_SOURCE_URL = "https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do"
OBSERVED_ARCHIVE = "raw/inundation/inundation_2022.zip"
EVENT_START_DATES = ("20220808", "20220809")
START_DATE = re.compile(r"^(\d{4})[-./]?(\d{2})[-./]?(\d{2})(?!\d)")
SEOUL_BOUNDARY_PATH = Path(__file__).resolve().parents[2] / "Dataset/processed/seoul_boundary_2025.geojson"


@lru_cache(maxsize=1)
def seoul_administrative_boundary():
    """Return the SGIS Seoul municipality boundary used for map context."""
    with SEOUL_BOUNDARY_PATH.open(encoding="utf-8") as source:
        return json.load(source)


@lru_cache(maxsize=2)
def _event_records(path, modified_ns):
    with ZipFile(path, metadata_encoding="cp949") as archive:
        stem = next(name[:-4] for name in archive.namelist() if name.lower().endswith(".shp"))
        crs = CRS.from_wkt(archive.read(stem + ".prj").decode("ascii"))
        with shapefile.Reader(
            shp=BytesIO(archive.read(stem + ".shp")), shx=BytesIO(archive.read(stem + ".shx")),
            dbf=BytesIO(archive.read(stem + ".dbf")), encoding="cp949", encodingErrors="replace",
        ) as source:
            records = []
            for entry in source.iterShapeRecords(fields=["F_YR", "F_SAT_YMD"]):
                match = START_DATE.match(entry.record["F_SAT_YMD"].strip())
                if entry.record["F_YR"] != "2022" or not match or "".join(match.groups()) not in EVENT_START_DATES:
                    continue
                if entry.shape.shapeType not in (shapefile.POLYGON, shapefile.POLYGONM, shapefile.POLYGONZ):
                    continue
                records.append((tuple(entry.shape.bbox), entry.shape.__geo_interface__))
    return crs, tuple(records)


def _geometries(dataset, bounds, target_crs):
    path = dataset / OBSERVED_ARCHIVE
    source_crs, records = _event_records(path, path.stat().st_mtime_ns)
    if bounds is not None:
        west, south, east, north = transform_bounds("EPSG:4326", source_crs, *bounds)
        records = (
            (bbox, geometry) for bbox, geometry in records
            if bbox[0] <= east and bbox[1] <= north and bbox[2] >= west and bbox[3] >= south
        )
    geometries = [geometry for _, geometry in records]
    if not geometries:
        return []
    collection = {"type": "GeometryCollection", "geometries": geometries}
    return transform_geom(source_crs, target_crs, collection)["geometries"]


def _map_geometry(geometry):
    def polygon(rings):
        return [[[round(lon, 6), round(lat, 6)] for lon, lat in ring] for ring in rings]

    coordinates = geometry["coordinates"]
    return {
        "type": geometry["type"],
        "coordinates": polygon(coordinates) if geometry["type"] == "Polygon" else [
            polygon(rings) for rings in coordinates
        ],
    }


def observed_geojson(dataset, bounds=None):
    return {
        "type": "FeatureCollection",
        "source": OBSERVED_SOURCE,
        "source_url": OBSERVED_SOURCE_URL,
        "event_start_dates": ["2022-08-08", "2022-08-09"],
        "features": [
            {"type": "Feature", "properties": {}, "geometry": _map_geometry(geometry)}
            for geometry in _geometries(dataset, bounds, "EPSG:4326")
        ],
    }


def observed_overlap(dataset, grid, maximum_depth, threshold_m=0.05):
    """Measure positive-record coverage using the union of recorded polygons at cell centers."""
    from .data import CELL_M, SEOUL_CRS

    geometries = _geometries(dataset, grid.wgs_bounds, SEOUL_CRS)
    footprint = rasterize(
        geometries, out_shape=grid.valid.shape, transform=grid.affine, fill=0,
        default_value=1, all_touched=False, dtype="uint8",
    ).astype(bool) if geometries else np.zeros_like(grid.valid)
    footprint &= grid.valid
    modeled = grid.valid & (np.asarray(maximum_depth).reshape(grid.valid.shape) >= threshold_m)
    observed_cells = int(np.count_nonzero(footprint))
    overlap_cells = int(np.count_nonzero(footprint & modeled))
    return {
        "source": OBSERVED_SOURCE,
        "source_url": OBSERVED_SOURCE_URL,
        "threshold_m": threshold_m,
        "observed_cells": observed_cells,
        "modeled_cells": int(np.count_nonzero(modeled)),
        "overlap_cells": overlap_cells,
        "observed_area_m2": observed_cells * CELL_M**2,
        "overlap_area_m2": overlap_cells * CELL_M**2,
        "observed_coverage": overlap_cells / observed_cells if observed_cells else None,
    }
