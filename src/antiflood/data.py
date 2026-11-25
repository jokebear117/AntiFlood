"""Load the original DEM, gauge observations, and optional effective drainage raster."""

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import TextIOWrapper
from functools import partial
from itertools import groupby
import os
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.merge import merge
from contextlib import ExitStack
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform, transform_bounds, transform_geom
import shapefile

from . import drainage as drainage_module

ROOT = Path(__file__).resolve().parents[2]
SEOUL_CRS = CRS.from_epsg(5181)
KST = timezone(timedelta(hours=9))
INTERVAL = timedelta(minutes=10)
CELL_M = 30.0
MAX_GAUGE_DISTANCE_M = 12_000.0
DEFAULT_BOUNDS = (126.75, 37.42, 127.20, 37.71)
MAX_CELLS = 1_650_000
SEOUL_PADDING_CELLS = 25
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
    drain_mm_h: np.ndarray | None = None
    drain_class: np.ndarray | None = None
    drainage_summary: dict | None = None


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
    dataset: Path
    gauge_codes: tuple[str, ...]
    start: datetime
    end: datetime
    interval_count: int

    def iter_intervals(self):
        return iter_rain_intervals(self.dataset, self.gauge_codes, self.start, self.end)

    def summary(self):
        return {
            "id": self.id,
            "title": self.title,
            "start": utc(self.start),
            "end": utc(self.end),
            "interval_count": self.interval_count,
            "rainfall_source": "서울시 OA-1168 · 10분 우량",
        }


def utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def dataset_dir():
    return Path(os.getenv("ANTIFLOOD_DATASET", ROOT / "Dataset")).resolve()


def dem_paths(dataset):
    return sorted((dataset / "raw/dem").glob("N37E12[67]_FABDEM_V1-2.tif"))


def read_elevation(dataset, destination, affine, crs):
    """Merge only the requested window, so the longitude seam is interpolated together."""
    paths = dem_paths(dataset)
    if not paths:
        raise ValueError("FABDEM 타일이 없습니다. 데이터 준비 명령을 실행해 주세요.")
    height, width = destination.shape
    bounds = transform_bounds(crs, "EPSG:4326", *rasterio.transform.array_bounds(height, width, affine))
    pad = 2 / 3600
    bounds = (bounds[0]-pad, bounds[1]-pad, bounds[2]+pad, bounds[3]+pad)
    with ExitStack() as stack:
        sources = [stack.enter_context(rasterio.open(path)) for path in paths]
        mosaic, mosaic_affine = merge(sources, bounds=bounds, nodata=-9999)
        reproject(
            mosaic[0], destination, src_transform=mosaic_affine, src_crs=sources[0].crs,
            src_nodata=-9999, dst_transform=affine, dst_crs=crs,
            dst_nodata=np.nan, resampling=Resampling.bilinear,
        )


def seoul_mask(shape, affine, all_touched=True):
    from .observed import seoul_administrative_boundary

    geometry = seoul_administrative_boundary()["features"][0]["geometry"]
    projected = transform_geom("EPSG:4326", SEOUL_CRS, geometry)
    return rasterize([projected], out_shape=shape, transform=affine, all_touched=all_touched).astype(bool)


def seoul_domain(shape, affine):
    inside = seoul_mask(shape, affine)
    # Dilate on the projected grid to retain adjacent terrain on both sides of the city line.
    radius = SEOUL_PADDING_CELLS
    for axis in (0, 1):
        rows = np.moveaxis(inside, axis, 0)
        summed = np.cumsum(np.pad(rows, ((radius + 1, radius), (0, 0))), axis=0, dtype=np.int32)
        inside = np.moveaxis(summed[2 * radius + 1:] != summed[:-(2 * radius + 1)], 0, axis)
    return inside


def load_grid(dataset, *, bounds=None, drain_mm_h=None, boundary=None, use_drain_raster=True, drainage=None):
    bounds_setting = os.getenv("ANTIFLOOD_BOUNDS")
    if bounds is None:
        bounds = tuple(map(float, bounds_setting.split(","))) if bounds_setting else DEFAULT_BOUNDS
    bounds = tuple(bounds)
    if (
        len(bounds) != 4 or not all(np.isfinite(bounds))
        or not (126.7 <= bounds[0] < bounds[2] <= 127.2 and 37.4 <= bounds[1] < bounds[3] <= 37.72)
    ):
        raise ValueError("서울 주변 지원 범위(126.7–127.2°E, 37.4–37.72°N) 안에서 영역을 선택해 주세요.")
    needed = {f"N37E{longitude}_FABDEM_V1-2.tif" for longitude in range(int(np.floor(bounds[0])), int(np.ceil(bounds[2])))}
    missing = needed - {path.name for path in dem_paths(dataset)}
    if missing:
        raise ValueError("지형 데이터가 없는 영역입니다. 필요한 타일: " + ", ".join(sorted(missing)))

    west, south, east, north = transform_bounds("EPSG:4326", SEOUL_CRS, *bounds)
    width = int(np.ceil((east - west) / CELL_M))
    height = int(np.ceil((north - south) / CELL_M))
    if width * height > MAX_CELLS:
        raise ValueError("한 번에 165만 셀 이하가 되도록 계산 범위를 줄여 주세요.")
    affine = from_origin(west, north, CELL_M, CELL_M)
    boundary_mode = boundary if boundary is not None else os.getenv("ANTIFLOOD_BOUNDARY", "open")
    if boundary_mode not in ("open", "closed"):
        raise ValueError("외곽 설정은 open 또는 closed로 지정해 주세요.")
    padded_elevation = np.full((height + 2, width + 2), np.nan)
    padded_affine = affine * rasterio.Affine.translation(-1, -1)
    read_elevation(dataset, padded_elevation, padded_affine, SEOUL_CRS)

    # A projected axis-aligned array may cover more than the WGS84 request.
    if bounds == DEFAULT_BOUNDS:
        inside = seoul_domain(padded_elevation.shape, padded_affine)
        if inside[0].any() or inside[-1].any() or inside[:, 0].any() or inside[:, -1].any():
            raise ValueError("서울 계산 영역과 여유 지형이 격자 안에 들어오지 않습니다.")
    else:
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
    if (inside[1:-1, 1:-1] & ~np.isfinite(elevation)).any():
        raise ValueError("선택 영역에 DEM NoData가 있습니다. 범위를 줄여 주세요.")
    exterior = np.where(~inside, padded_elevation, np.nan)
    if boundary_mode == "closed":
        exterior[:] = np.nan
    boundary_elevation = np.ascontiguousarray(np.stack((
        exterior[1:-1, 2:], exterior[:-2, 1:-1], exterior[1:-1, :-2], exterior[2:, 1:-1],
    ), axis=-1))

    default_rate = float(drain_mm_h if drain_mm_h is not None else os.getenv("ANTIFLOOD_DRAIN_MM_H", "5"))
    if not np.isfinite(default_rate) or default_rate < 0:
        raise ValueError("기본 배수율은 0 이상의 mm/h 값이어야 합니다.")
    rates = np.full_like(elevation, np.nan)
    raster_source = os.getenv("ANTIFLOOD_DRAIN_RASTER_SOURCE", "assumed")
    if raster_source not in ("observed", "assumed"):
        raise ValueError("배수율 출처는 observed 또는 assumed로 지정해 주세요.")
    rate_path = os.getenv("ANTIFLOOD_DRAIN_RASTER") if use_drain_raster else None
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
    drainage = drainage or os.getenv("ANTIFLOOD_DRAINAGE", "facility")
    if drainage not in ("facility", "uniform"):
        raise ValueError("배수 방식은 facility 또는 uniform으로 지정해 주세요.")
    supplied = valid & np.isfinite(rates)
    if rate_path or drainage == "uniform":
        source_type = "assumed"
        if raster_source == "observed" and supplied.any():
            source_type = "observed" if supplied.sum() == valid.sum() else "mixed"
        mm_h = np.where(valid, np.where(supplied, rates, default_rate), 0)
        classes = np.where(valid & supplied & (raster_source == "observed"), drainage_module.SEWER,
                           drainage_module.ASSUMED).astype(np.uint8)
        fallback = int((valid & ~supplied).sum())
    else:
        source_type = "facility"
        mm_h, classes = drainage_module.facility_rates(dataset, valid, affine, default_rate)
        fallback = int((valid & (classes == drainage_module.ASSUMED)).sum())
    # The native engine takes float64; the raster stores float32.
    drain = np.ascontiguousarray(mm_h, dtype=np.float64) / 3_600_000
    return GridData(
        elevation, valid, affine, boundary_elevation, boundary_mode, drain, source_type, default_rate,
        raster_source if rate_path else None, fallback, bounds,
        mm_h.astype(np.float32), classes, drainage_module.summary(mm_h, classes, valid),
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


def _rain_rows(source, gauge_index, start, end):
    previous = None
    for row in csv.DictReader(source):
        index = gauge_index.get(row["강우량계 코드"].strip())
        if index is None:
            continue
        observed_at = datetime.fromisoformat(row["자료수집 시각"]).replace(tzinfo=KST)
        if observed_at.minute % 10 != 9 or observed_at.second:
            continue
        time = observed_at - timedelta(minutes=9)
        if previous is not None and time < previous:
            raise ValueError("강우 입력이 시간순으로 정렬되어 있지 않습니다.")
        previous = time
        if start <= time < end:
            yield time, index, row["10분우량"].strip()


def _rain_interval(gauge_count, group):
    time, rows = group
    amounts = np.full(gauge_count, np.nan)
    for _, index, text in rows:
        if not text:
            continue
        amount = float(text)
        if not np.isfinite(amount) or amount < 0:
            raise ValueError(f"강우량 값이 유효하지 않습니다. {time} / gauge {index}")
        if not np.isnan(amounts[index]) and amounts[index] != amount:
            raise ValueError(f"같은 시각의 강우량이 서로 다릅니다. {time} / gauge {index}")
        amounts[index] = amount
    if np.isfinite(amounts).all():
        return RainInterval(time, time + INTERVAL, time + timedelta(minutes=9), amounts)
    return None


def iter_rain_intervals(dataset, gauge_codes, start=RAIN_START, end=RAIN_END):
    """Read one complete bin at a time; no yielded rainfall array is retained.

    The source CSV must be chronological. Missing gauges split scenarios rather
    than being filled with zero. Reopening gives Reference an independent pass.
    """
    gauge_index = {code: index for index, code in enumerate(gauge_codes)}
    path = dataset / "raw/rainfall/rainfall_2022.zip"
    with ZipFile(path, metadata_encoding="cp949") as archive:
        name = next(name for name in archive.namelist() if name.endswith("08월.csv"))
        with TextIOWrapper(archive.open(name), encoding="cp949", newline="") as source:
            groups = groupby(_rain_rows(source, gauge_index, start, end), key=lambda row: row[0])
            # map/filter keep no reference to their previously returned array.
            yield from filter(None, map(partial(_rain_interval, len(gauge_codes)), groups))


def load_scenarios(dataset, gauges):
    gauge_codes = tuple(gauge[0] for gauge in gauges)
    runs = []
    start = end = None
    count = 0
    peak = 0.0
    for interval in iter_rain_intervals(dataset, gauge_codes):
        if end is not None and interval.start != end:
            runs.append((start, end, count, peak))
            start = None
            count = 0
            peak = 0.0
        if start is None:
            start = interval.start
        end = interval.end
        count += 1
        peak = max(peak, float(interval.gauge_mm.max()))
        del interval
    if start is not None:
        runs.append((start, end, count, peak))
    if not runs:
        raise ValueError("계산 영역에 필요한 관측소의 강우가 모두 있는 10분 구간이 없습니다.")
    main = max(range(len(runs)), key=lambda index: runs[index][3])
    result = []
    for index in [main, *(index for index in range(len(runs)) if index != main)]:
        start, end, count, _ = runs[index]
        result.append(Scenario(
            "seoul_2022_aug" if index == main else f"seoul_2022_aug_{index + 1}",
            f"{start:%m.%d %H:%M} ~ {end:%m.%d %H:%M} KST",
            dataset, gauge_codes, start, end, count,
        ))
    return result
