"""Build and read the 30 m effective drainage capacity raster for Seoul.

The rate is a design-based estimate, not an observed outflow:
- Seoul cells use the branch-sewer design intensity in force in August 2022 (10-year, 78.7 mm/h).
- Cells inside an approximate pump-station catchment are capped by that district's pump
  capacity divided by its pump-drained basin area.
- Cells outside the Seoul boundary have no facility data and keep the user's assumed rate.

The raster is written once to Dataset/processed and reprojected onto each run grid, so the
map layer and the engine input come from the same array.
"""

import csv
from functools import lru_cache
from io import BytesIO
from zipfile import ZipFile

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform
import shapefile

# 2040 서울특별시 하수도정비기본계획 탄천처리구역, 표 4.6-131 (2030 기본계획 적용값, 10년 빈도).
# The plan states branch sewers were designed for 10-year and trunk sewers for 30-year return periods.
SEWER_BRANCH_MM_H = 78.7
# Design capacity is converted to surface drainage without reduction. The model has no
# infiltration loss, so all surface water is drainage demand; the sewer design intensity and the
# pump discharge per drained area are both already expressed per unit surface area. Inlet
# clogging or partial operation would lower the factor, but no source quantifies it for 2022.
EFFECTIVE_FACTOR = 1.0
SEWER_SOURCE = "2040 서울시 하수도정비기본계획 표 4.6-131, 지선 설계빈도 10년 강우강도"
PUMP_SOURCE = "김응석, 이승현(2022) 한국방재학회논문집 22(5) Table 2, 자치구별 빗물펌프장 용량(2014년 기준)"
PUMP_LOCATION_SOURCE = "서울시 OA-21179 빗물펌프장 위치 (EPSG:5186)"
PUMP_CRS = "EPSG:5186"
RASTER_NAME = "processed/seoul_drainage_capacity_30m.tif"
ASSUMED, SEWER, PUMP = range(3)
CLASS_NAMES = ("assumed", "sewer", "pump")


@lru_cache(maxsize=1)
def district_capacity(dataset):
    path = dataset / "processed/seoul_pump_capacity_by_district.csv"
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    result = {}
    for row in rows:
        area_ha = float(row["pump_basin_area_ha"])
        capacity = float(row["pump_capacity_m3_min"])
        result[int(row["district_code"])] = {
            "district": row["district"],
            "area_ha": area_ha,
            "capacity_m3_min": capacity,
            # m3/min over ha converted to an equivalent rainfall rate in mm/h.
            "rate_mm_h": capacity * 6 / area_ha,
        }
    return result


@lru_cache(maxsize=1)
def pump_stations(dataset):
    """Return pump points in EPSG:5181 with the district coded in the ETC prefix."""
    from .data import SEOUL_CRS

    path = dataset / "raw/drainage/RAINPUMP.zip"
    if not path.is_file():
        raise ValueError("빗물펌프장 위치 자료가 없습니다. 데이터 준비 명령을 실행하거나 균일 가정 배수율을 선택해 주세요.")
    with ZipFile(path) as archive:
        with shapefile.Reader(
            shp=BytesIO(archive.read("RAINPUMP.shp")), shx=BytesIO(archive.read("RAINPUMP.shx")),
            dbf=BytesIO(archive.read("RAINPUMP.dbf")), encoding="cp949",
        ) as source:
            records = [
                (item.record["PUMP_NM"].strip(), str(item.record["ETC"]).strip(), *item.shape.points[0])
                for item in source.iterShapeRecords()
            ]
    capacity = district_capacity(dataset)
    xs, ys = transform(PUMP_CRS, SEOUL_CRS, [r[2] for r in records], [r[3] for r in records])
    lons, lats = transform(PUMP_CRS, "EPSG:4326", [r[2] for r in records], [r[3] for r in records])
    counts = {}
    for _, code, *_ in records:
        if code.isdigit():
            counts[int(code) // 100] = counts.get(int(code) // 100, 0) + 1
    stations = []
    for (name, code, *_), x, y, lon, lat in zip(records, xs, ys, lons, lats):
        district = int(code) // 100 if code.isdigit() else None
        info = capacity.get(district)
        # Split the district's pump-drained area equally between its listed stations.
        radius = float(np.sqrt(info["area_ha"] * 10_000 / (counts[district] * np.pi))) if info else None
        stations.append({
            "name": name, "district": info["district"] if info else None, "x": x, "y": y,
            "lon": lon, "lat": lat, "radius_m": radius, "stations_in_district": counts.get(district),
            "rate_mm_h": info["rate_mm_h"] if info else None,
            "capacity_m3_min": info["capacity_m3_min"] if info else None,
            "area_ha": info["area_ha"] if info else None,
        })
    return tuple(stations)


def nearest_station(dataset, x, y):
    """Return the closest pump station that has district capacity data, with its distance."""
    stations = [item for item in pump_stations(dataset) if item["radius_m"] is not None]
    distances = [np.hypot(x - item["x"], y - item["y"]) for item in stations]
    index = int(np.argmin(distances))
    return stations[index], float(distances[index])


def design_rates(dataset, valid, affine, seoul):
    """Return the design drainage rate (mm/h) and class for Seoul cells; others are NaN/ASSUMED."""
    from .data import CELL_M

    rates = np.full(valid.shape, np.nan)
    classes = np.full(valid.shape, ASSUMED, dtype=np.uint8)
    inside = valid & seoul
    rates[inside] = SEWER_BRANCH_MM_H
    classes[inside] = SEWER
    rows, cols = np.nonzero(inside)
    x = affine.c + (cols + 0.5) * CELL_M
    y = affine.f - (rows + 0.5) * CELL_M
    nearest = np.full(rows.size, np.inf)
    cap = np.full(rows.size, np.inf)
    for station in pump_stations(dataset):
        if station["radius_m"] is None:
            continue
        distance = np.hypot(x - station["x"], y - station["y"])
        closer = distance < nearest
        nearest[closer] = distance[closer]
        cap[closer] = np.where(distance[closer] <= station["radius_m"], station["rate_mm_h"], np.inf)
    limited = cap < SEWER_BRANCH_MM_H
    rates[rows[limited], cols[limited]] = cap[limited]
    classes[rows[limited], cols[limited]] = PUMP
    return rates, classes


def raster_path(dataset):
    return dataset / RASTER_NAME


def build_raster(dataset):
    """Write the Seoul-wide raster on the default 30 m DEM grid (EPSG:5181)."""
    from .data import DEFAULT_BOUNDS, SEOUL_CRS, load_grid, seoul_mask

    grid = load_grid(dataset, bounds=DEFAULT_BOUNDS, drainage="uniform", use_drain_raster=False, boundary="open")
    seoul = seoul_mask(grid.valid.shape, grid.affine, all_touched=False)
    design, classes = design_rates(dataset, grid.valid, grid.affine, seoul)
    effective = design * EFFECTIVE_FACTOR
    path = raster_path(dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(".tmp.tif")
    profile = {
        "driver": "GTiff", "dtype": "float32", "count": 3, "crs": SEOUL_CRS, "transform": grid.affine,
        "height": grid.valid.shape[0], "width": grid.valid.shape[1], "nodata": np.nan,
        "compress": "deflate", "predictor": 3, "tiled": True,
    }
    with rasterio.open(pending, "w", **profile) as target:
        target.write(effective.astype(np.float32), 1)
        target.write(design.astype(np.float32), 2)
        target.write(np.where(classes == ASSUMED, np.nan, classes).astype(np.float32), 3)
        target.set_band_description(1, "effective_drainage_mm_h")
        target.set_band_description(2, "design_drainage_mm_h")
        target.set_band_description(3, "source_1_sewer_2_pump")
        target.update_tags(
            units="mm/h", reference_year="2022 facilities; pump capacity table 2014",
            effective_factor=str(EFFECTIVE_FACTOR), sewer_source=SEWER_SOURCE, pump_source=PUMP_SOURCE,
            pump_location_source=PUMP_LOCATION_SOURCE,
            method="Seoul cells: branch sewer 10-year design intensity. Within an equal-area circle "
                   "around each pump station: min(sewer, district pump m3/min x 6 / basin ha). "
                   "Outside Seoul: NoData (the run uses the assumed rate).",
        )
    pending.replace(path)
    return path


def ensure_raster(dataset):
    path = raster_path(dataset)
    inputs = [dataset / "processed/seoul_pump_capacity_by_district.csv", dataset / "raw/drainage/RAINPUMP.zip"]
    if not path.is_file() or any(item.is_file() and item.stat().st_mtime > path.stat().st_mtime for item in inputs):
        build_raster(dataset)
    return path


def facility_rates(dataset, valid, affine, fallback_mm_h):
    """Reproject the raster onto a run grid. Returns effective mm/h and source class per cell."""
    from .data import SEOUL_CRS

    bands = np.full((3, *valid.shape), np.nan, dtype=np.float32)
    with rasterio.open(ensure_raster(dataset)) as source:
        for band in range(3):
            reproject(
                rasterio.band(source, band + 1), bands[band], dst_transform=affine, dst_crs=SEOUL_CRS,
                dst_nodata=np.nan, resampling=Resampling.nearest,
            )
    covered = valid & np.isfinite(bands[0])
    rates = np.where(covered, bands[0], float(fallback_mm_h))
    classes = np.where(covered, np.nan_to_num(bands[2]), ASSUMED).astype(np.uint8)
    rates[~valid] = 0
    return rates, classes


def explain(dataset, x, y, rate, source, fallback_mm_h=None):
    """Describe how the rate at a point (EPSG:5181 metres) was obtained."""
    if source == SEWER:
        return (f"지선 하수관 10년 빈도 설계 강우강도 {SEWER_BRANCH_MM_H} mm/h. 출처: {SEWER_SOURCE}. "
                "2022년 당시 지선 10년, 간선 30년 빈도 설계 기준.")
    if source == PUMP:
        station, distance = nearest_station(dataset, x, y)
        return (f"{station['district']} 빗물펌프장 용량 {station['capacity_m3_min']:,.0f} m³/분 ÷ 펌프 배수면적 "
                f"{station['area_ha']:,.1f} ha = {station['rate_mm_h']:.1f} mm/h. 가장 가까운 펌프장 {station['name']}"
                f"({distance:,.0f} m), 배수구역 근사 반경 {station['radius_m']:,.0f} m. 출처: {PUMP_SOURCE}.")
    return f"서울 밖이라 시설 자료가 없어 가정값 {rate:g} mm/h를 적용."


def summary(rates, classes, valid):
    counts = {name: int(np.count_nonzero(valid & (classes == code))) for code, name in enumerate(CLASS_NAMES)}
    values = rates[valid]
    return {
        "cells": counts,
        "mean_mm_h": float(values.mean()) if values.size else None,
        "min_mm_h": float(values.min()) if values.size else None,
        "max_mm_h": float(values.max()) if values.size else None,
        "sewer_mm_h": SEWER_BRANCH_MM_H,
        "effective_factor": EFFECTIVE_FACTOR,
        "raster": RASTER_NAME,
        "sources": [SEWER_SOURCE, PUMP_SOURCE, PUMP_LOCATION_SOURCE],
    }


def pump_geojson(dataset):
    return {
        "type": "FeatureCollection",
        "source": PUMP_LOCATION_SOURCE,
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": item["name"], "district": item["district"],
                    "rate_mm_h": None if item["rate_mm_h"] is None else round(item["rate_mm_h"], 1),
                    "radius_m": None if item["radius_m"] is None else round(item["radius_m"]),
                },
                "geometry": {"type": "Point", "coordinates": [round(item["lon"], 6), round(item["lat"], 6)]},
            }
            for item in pump_stations(dataset)
        ],
    }


if __name__ == "__main__":
    from .data import dataset_dir

    print(build_raster(dataset_dir()))
