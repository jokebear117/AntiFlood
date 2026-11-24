"""Estimate per-cell effective drainage capacity from public sewer and pump-station data.

The rate is a design-based estimate, not an observed outflow:
- Seoul cells use the branch-sewer design intensity in force in August 2022 (10-year, 78.7 mm/h).
- Cells inside an approximate pump-station catchment are capped by that district's pump
  capacity divided by its pump-drained basin area.
- Cells outside the Seoul boundary keep the user's assumed rate.
"""

import csv
from functools import lru_cache
from io import BytesIO
from zipfile import ZipFile

import numpy as np
import shapefile
from rasterio.warp import transform

# 2040 서울특별시 하수도정비기본계획 탄천처리구역, 표 4.6-131 (2030 기본계획 적용값, 10년 빈도).
# The plan states branch sewers were designed for 10-year and trunk sewers for 30-year return periods.
SEWER_BRANCH_MM_H = 78.7
SEWER_SOURCE = "2040 서울시 하수도정비기본계획 표 4.6-131, 지선 설계빈도 10년 강우강도"
PUMP_SOURCE = "김응석, 이승현(2022) 한국방재학회논문집 22(5) Table 2, 자치구별 빗물펌프장 용량"
PUMP_LOCATION_SOURCE = "서울시 OA-21179 빗물펌프장 위치 (EPSG:5186)"
PUMP_CRS = "EPSG:5186"
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
            "basin_area_m2": area_ha * 10_000,
            "capacity_m3_s": capacity / 60,
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
        radius = float(np.sqrt(info["basin_area_m2"] / (counts[district] * np.pi))) if info else None
        stations.append({
            "name": name, "district": info["district"] if info else None, "x": x, "y": y,
            "lon": lon, "lat": lat, "radius_m": radius,
            "rate_mm_h": info["rate_mm_h"] if info else None,
        })
    return tuple(stations)


def facility_rates(dataset, valid, affine, seoul, fallback_mm_h):
    """Return the effective drainage rate (mm/h) and source class for each cell."""
    from .data import CELL_M

    rates = np.full(valid.shape, float(fallback_mm_h))
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
    rates[~valid] = 0
    return rates, classes


def summary(rates, classes, valid):
    counts = {name: int(np.count_nonzero(valid & (classes == code))) for code, name in enumerate(CLASS_NAMES)}
    values = rates[valid]
    return {
        "cells": counts,
        "mean_mm_h": float(values.mean()) if values.size else None,
        "min_mm_h": float(values.min()) if values.size else None,
        "max_mm_h": float(values.max()) if values.size else None,
        "sewer_mm_h": SEWER_BRANCH_MM_H,
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
