"""Read immutable run metadata and frames independently of the live simulation."""

import json
import re

import numpy as np
from rasterio import Affine
from rasterio.warp import transform

RUN_ID = re.compile(r"[0-9a-f]{32}")


def run_directory(root, run_id):
    if not RUN_ID.fullmatch(run_id):
        raise FileNotFoundError("실행 ID가 올바르지 않습니다.")
    directory = root / run_id
    if not (directory / "run.json").is_file():
        raise FileNotFoundError("저장된 실행을 찾을 수 없습니다.")
    return directory


def read_run(root, run_id):
    directory = run_directory(root, run_id)
    info = json.loads((directory / "run.json").read_text(encoding="utf8"))
    frames = []
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9][0-9].json")):
        if path.with_suffix(".npy").is_file() and path.with_suffix(".png").is_file():
            frame = json.loads(path.read_text(encoding="utf8"))
            frame.pop("active_tiles", None)
            frames.append(frame)
    return info, frames


def saved_point(directory, stem, longitude, latitude):
    info = json.loads((directory / "run.json").read_text(encoding="utf8"))
    meta = info["map"]
    affine = Affine(*meta["grid_transform"])
    x, y = transform("EPSG:4326", meta["grid_crs"], [longitude], [latitude])
    col, row = (~affine) * (x[0], y[0])
    row, col = int(np.floor(row)), int(np.floor(col))
    valid_path = directory / "valid.npy"
    if not valid_path.exists():
        raise ValueError("이전 형식의 결과에 영역 마스크가 없습니다. 설정을 재사용해 다시 계산해 주세요.")
    valid = np.load(valid_path, mmap_mode="r")
    if not (0 <= row < valid.shape[0] and 0 <= col < valid.shape[1] and valid[row, col]):
        return None
    depth = np.load(directory / f"{stem}.npy", mmap_mode="r")
    frame = json.loads((directory / f"{stem}.json").read_text(encoding="utf8"))
    center_x, center_y = affine * (col + .5, row + .5)
    tile_id = f"{int(np.floor(center_x/100))}_{int(np.floor(center_y/100))}"
    rain = []
    mapping = directory / "gauge_map.npy"
    if mapping.is_file():
        index = int(np.load(mapping, mmap_mode="r")[row,col])
        gauge = info["gauges"][index]
        rain = [{"station_id":gauge["id"], "name":gauge["name"], "mm":frame["rain_interval_mm"][index]}]
    return {"tile_id":tile_id,"depth_m":float(depth[row,col]),"time":frame["time"],
            "active":tile_id in frame["active_tiles"],"rain":rain}
