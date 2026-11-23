"""Load the original DEM, gauge observations, and optional effective drainage raster."""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import TextIOWrapper
import os
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform, transform_bounds
import shapefile

ROOT = Path(__file__).resolve().parents[2]
SEOUL_CRS = CRS.from_epsg(5181)
KST = timezone(timedelta(hours=9))
INTERVAL = timedelta(minutes=10)
CELL_M = 30.0
MAX_GAUGE_DISTANCE_M = 12_000.0
DEFAULT_BOUNDS = (127.005, 37.470, 127.065, 37.535)
RAIN_START = datetime(2022, 8, 8, tzinfo=KST)
RAIN_END = datetime(2022, 8, 10, tzinfo=KST)


@dataclass(frozen=True)
class GridData:
    elevation: np.ndarray
    valid: np.ndarray
    affine: rasterio.Affine
    boundary_elevation: np.ndarray
    boundary_mode: str
    drain: np.ndarray
    drainage_source: str
    default_drain_mm_h: float
    drainage_raster_source: str | None
    drainage_fallback_cells: int
    wgs_bounds: tuple[float, float, float, float]


@dataclass(frozen=True)
class RainInterval:
    start: datetime
    end: datetime
    observed_at: datetime
    gauge_mm: np.ndarray


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    intervals: tuple[RainInterval, ...]

    def summary(self):
        return {
            "id": self.id,
            "title": self.title,
            "start": utc(self.intervals[0].start),
            "end": utc(self.intervals[-1].end),
            "interval_count": len(self.intervals),
            "rainfall_source": "서울시 OA-1168 · 10분 우량",
        }


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def dataset_dir():
    return Path(os.getenv("ANTIFLOOD_DATASET", ROOT / "Dataset")).resolve()


def load_grid(dataset):
    raw_dem = dataset / "raw/dem/N37E127_FABDEM_V1-2.tif"
    dem_path = raw_dem if raw_dem.exists() else dataset / "processed/fabdem_gangnam_1arcsec.tif"
    bounds_setting = os.getenv("ANTIFLOOD_BOUNDS")
    if bounds_setting:
        dem_path = raw_dem
    bounds = tuple(map(float, bounds_setting.split(","))) if bounds_setting else DEFAULT_BOUNDS
    if (
        len(bounds) != 4 or not all(np.isfinite(bounds))
        or not (127 <= bounds[0] < bounds[2] <= 128 and 37 <= bounds[1] < bounds[3] <= 38)
    ):
        raise ValueError("ANTIFLOOD_BOUNDS에 FABDEM 타일 안의 서·남·동·북 경위도를 입력해 주세요.")

    west, south, east, north = transform_bounds("EPSG:4326", SEOUL_CRS, *bounds)
    width = int(np.ceil((east - west) / CELL_M))
    height = int(np.ceil((north - south) / CELL_M))
    if width * height > 1_000_000:
        raise ValueError("한 번에 100만 셀 이하가 되도록 계산 범위를 줄여 주세요.")
    affine = from_origin(west, north, CELL_M, CELL_M)
    boundary_mode = os.getenv("ANTIFLOOD_BOUNDARY", "open")
    if boundary_mode not in ("open", "closed"):
        raise ValueError("외곽 설정은 open 또는 closed로 지정해 주세요.")
    padded_elevation = np.full((height + 2, width + 2), np.nan)
    padded_affine = affine * rasterio.Affine.translation(-1, -1)
    with rasterio.open(dem_path) as source:
        if not source.crs:
            raise ValueError("DEM에 좌표계가 지정되어야 합니다.")
        reproject(
            rasterio.band(source, 1), padded_elevation,
            dst_crs=SEOUL_CRS, dst_transform=padded_affine, dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )

    # A projected axis-aligned array may cover more than the WGS84 request.
    rows, cols = np.indices(padded_elevation.shape, dtype=np.float64)
    x = padded_affine.c + (cols + 0.5) * CELL_M
    y = padded_affine.f - (rows + 0.5) * CELL_M
    lon, lat = np.asarray(transform(SEOUL_CRS, "EPSG:4326", x.ravel(), y.ravel()))
    inside = (
        (lon >= bounds[0]) & (lon <= bounds[2]) & (lat >= bounds[1]) & (lat <= bounds[3])
    ).reshape(padded_elevation.shape)
    elevation = np.ascontiguousarray(padded_elevation[1:-1, 1:-1])
    valid = np.isfinite(elevation) & inside[1:-1, 1:-1]
    if not valid.any():
        raise ValueError("지정한 범위에 유효한 DEM 셀이 없습니다.")
    exterior = np.where(~inside, padded_elevation, np.nan)
    if boundary_mode == "closed":
        exterior[:] = np.nan
    boundary_elevation = np.ascontiguousarray(np.stack((
        exterior[1:-1, 2:], exterior[:-2, 1:-1], exterior[1:-1, :-2], exterior[2:, 1:-1],
    ), axis=-1))

    default_rate = float(os.getenv("ANTIFLOOD_DRAIN_MM_H", "5"))
    if not np.isfinite(default_rate) or default_rate < 0:
        raise ValueError("기본 배수율은 0 이상의 mm/h 값이어야 합니다.")
    rates = np.full_like(elevation, np.nan)
    raster_source = os.getenv("ANTIFLOOD_DRAIN_RASTER_SOURCE", "assumed")
    if raster_source not in ("observed", "assumed"):
        raise ValueError("배수율 출처는 observed 또는 assumed로 지정해 주세요.")
    rate_path = os.getenv("ANTIFLOOD_DRAIN_RASTER")
    if rate_path:
        with rasterio.open(rate_path) as source:
            if not source.crs:
                raise ValueError("배수율 GeoTIFF에 좌표계가 지정되어야 합니다.")
            reproject(
                rasterio.band(source, 1), rates,
                dst_crs=SEOUL_CRS, dst_transform=affine, dst_nodata=np.nan,
                resampling=Resampling.nearest,
            )
        if np.any(rates[valid & np.isfinite(rates)] < 0):
            raise ValueError("배수율 GeoTIFF에 음수 값이 있습니다.")
    supplied = valid & np.isfinite(rates)
    source_type = "assumed"
    if raster_source == "observed" and supplied.any():
        source_type = "observed" if supplied.sum() == valid.sum() else "mixed"
    drain = np.where(valid, np.where(supplied, rates, default_rate) / 3_600_000, 0)
    return GridData(
        elevation, valid, affine, boundary_elevation, boundary_mode, drain, source_type, default_rate,
        raster_source if rate_path else None, int((valid & ~supplied).sum()), bounds,
    )


def load_gauges(dataset, grid):
    path = dataset / "raw/rainfall/stations_epsg5181.zip"
    with ZipFile(path) as archive:
        with shapefile.Reader(
            shp=archive.open("seoul_rain.shp"), dbf=archive.open("seoul_rain.dbf"), encoding="cp949",
        ) as shapes:
            gauges = sorted(
                (str(item.record["GAUGE_CODE"]), *item.shape.points[0], item.record["S_NAME"].split(" (")[0])
                for item in shapes.iterShapeRecords()
            )
    if not gauges or len({gauge[0] for gauge in gauges}) != len(gauges):
        raise ValueError("관측소 좌표 파일에 관측소가 없거나 관측소 코드가 중복됩니다.")
    rows, cols = np.indices(grid.valid.shape)
    x = grid.affine.c + (cols + 0.5) * CELL_M
    y = grid.affine.f - (rows + 0.5) * CELL_M
    nearest = np.zeros(grid.valid.shape, dtype=np.int32)
    distance_sq = np.full(grid.valid.shape, np.inf)
    for index, (_, gauge_x, gauge_y, _) in enumerate(gauges):
        candidate = (x - gauge_x) ** 2 + (y - gauge_y) ** 2
        closer = candidate < distance_sq
        distance_sq[closer] = candidate[closer]
        nearest[closer] = index
    if distance_sq[grid.valid].max() > MAX_GAUGE_DISTANCE_M ** 2:
        raise ValueError("12 km 이내에 서울시 강우 관측소가 있도록 계산 범위를 줄여 주세요.")
    used, inverse = np.unique(nearest[grid.valid], return_inverse=True)
    nearest[grid.valid] = inverse.ravel()
    nearest[~grid.valid] = -1
    return tuple(gauges[index] for index in used), nearest


def load_scenarios(dataset, gauges):
    gauge_index = {gauge[0]: index for index, gauge in enumerate(gauges)}
    values = {}
    path = dataset / "raw/rainfall/rainfall_2022.zip"
    with ZipFile(path, metadata_encoding="cp949") as archive:
        name = next(name for name in archive.namelist() if name.endswith("08월.csv"))
        with TextIOWrapper(archive.open(name), encoding="cp949", newline="") as source:
            for row in csv.DictReader(source):
                index = gauge_index.get(row["강우량계 코드"].strip())
                if index is None:
                    continue
                observed_at = datetime.fromisoformat(row["자료수집 시각"]).replace(tzinfo=KST)
                if not RAIN_START <= observed_at < RAIN_END:
                    continue
                # OA-1168 labels 00:09 as the 00:00–00:10 ten-minute bin.
                if observed_at.minute % 10 != 9 or observed_at.second:
                    continue
                start = observed_at - timedelta(minutes=9)
                if not row["10분우량"].strip():
                    continue
                amount = float(row["10분우량"])
                if not np.isfinite(amount) or amount < 0:
                    raise ValueError(f"강우량 값이 유효하지 않습니다. {observed_at} / {gauges[index][0]}")
                amounts = values.setdefault(start, np.full(len(gauges), np.nan))
                if not np.isnan(amounts[index]) and amounts[index] != amount:
                    raise ValueError(f"같은 시각의 강우량이 서로 다릅니다. {observed_at} / {gauges[index][0]}")
                amounts[index] = amount

    runs = []
    current = []
    time = RAIN_START
    while time < RAIN_END:
        amounts = values.get(time)
        if amounts is not None and np.isfinite(amounts).all():
            current.append(RainInterval(time, time + INTERVAL, time + timedelta(minutes=9), amounts))
        elif current:
            runs.append(tuple(current))
            current = []
        time += INTERVAL
    if current:
        runs.append(tuple(current))
    if not runs:
        raise ValueError("계산 영역에 필요한 관측소의 강우가 모두 있는 10분 구간이 없습니다.")
    main = max(range(len(runs)), key=lambda index: max(item.gauge_mm.max() for item in runs[index]))
    result = []
    for index in [main, *(index for index in range(len(runs)) if index != main)]:
        intervals = runs[index]
        result.append(Scenario(
            "seoul_2022_aug" if index == main else f"seoul_2022_aug_{index + 1}",
            f"{intervals[0].start:%m.%d %H:%M} ~ {intervals[-1].end:%m.%d %H:%M} KST",
            intervals,
        ))
    return result
