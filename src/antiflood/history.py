"""Read immutable run metadata and frames independently of the live simulation."""

import json
import re

import numpy as np
from rasterio import Affine
from rasterio.warp import transform
from .tiles import HALO

RUN_ID = re.compile(r"[0-9a-f]{32}")


def write_json(path, data):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    pending.replace(path)


def load_depth(directory, stem):
    compressed = directory / f"{stem}.npz"
    if compressed.is_file():
        with np.load(compressed) as arrays:
            return arrays["depth"]
    return np.load(directory / f"{stem}.npy", mmap_mode="r")


def tile_active(directory, stem, frame, index, tile_id):
    if frame.get("mode") == "reference":
        return True
    if frame.get("mode") == "streaming":
        with np.load(directory / f"{stem}.npz") as arrays:
            return bool(arrays["tile_modes"][index] >= HALO)
    return tile_id in frame["active_tiles"]


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
        if path.with_suffix(".npz").is_file() or (
            path.with_suffix(".npy").is_file() and path.with_suffix(".png").is_file()
        ):
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
    depth = load_depth(directory, stem)
    frame = json.loads((directory / f"{stem}.json").read_text(encoding="utf8"))
    center_x, center_y = affine * (col + .5, row + .5)
    tile_id = f"{int(np.floor(center_x/100))}_{int(np.floor(center_y/100))}"
    rain = []
    mapping = directory / "gauge_map.npy"
    tile_path = directory / "tile_map.npy"
    index = None
    detail = {"calculation_policy": frame.get("calculation_policy"),
              "last_step_seconds": frame.get("last_step_seconds")}
    if tile_path.is_file():
        tile_map = np.load(tile_path, mmap_mode="r")
        index = tile_map[row, col]
        window = np.s_[max(0, row-4):row+5, max(0, col-4):col+5]
        members = tile_map[window] == index
        gauge_indices = np.unique(np.load(mapping, mmap_mode="r")[window][members])
        with np.load(directory / f"{stem}.npz") as arrays:
            detail.update(
                tile_mode=int(arrays["tile_modes"][index]),
                reasons=int(arrays["tile_reasons"][index]),
                last_update_seconds=float(arrays["last_update"][index]),
                max_tile_depth_m=float(depth[window][members].max()),
                gauge_indices=gauge_indices.tolist(),
            )
        ref_id = info.get("reference_id")
        if ref_id and frame.get("reference_frame_id") == f"{ref_id}_{stem}":
            ref = float(load_depth(directory.parent / ref_id, stem)[row, col])
            detail.update(reference_depth_m=ref, difference_m=float(depth[row, col]) - ref)
        for name in ("rain_interval_mm", "sliding_mm", "decaying_mm"):
            detail[name] = max(frame[name][i] for i in gauge_indices)
    else:
        gauge_indices = [int(np.load(mapping, mmap_mode="r")[row, col])] if mapping.is_file() else []
    drainage = directory / "drainage.npz"
    if drainage.is_file():
        with np.load(drainage) as arrays:
            detail.update(drain_mm_h=float(arrays["rate"][row, col]),
                          drain_source=("assumed", "sewer", "pump")[int(arrays["source"][row, col])])
    for i in gauge_indices:
        gauge = info["gauges"][i]
        rain.append({"station_id":gauge["id"], "name":gauge["name"], "mm":frame["rain_interval_mm"][i]})
    return {
        "tile_id": tile_id, "depth_m": float(depth[row, col]), "time": frame["time"],
        "active": tile_active(directory, stem, frame, index, tile_id), "rain": rain, **detail,
    }
