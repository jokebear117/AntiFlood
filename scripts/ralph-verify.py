"""Independent acceptance for G01–G16, after implementation and final review.

Before a DONE candidate, the outer reviewer writes .ralph/runtime/final-review.json:
{"source_sha256": {"repository/relative/path": "sha256", ...},
 "criteria": {"G01": {"status": "VERIFIED", "evidence": ["relative/path", ...]}, ...}}

source_sha256 must cover all tracked engine/, src/, web/, docs/, scripts/, README.md,
AGENTS.md and pyproject.toml files at review time. Evidence paths must exist inside
the repository. The review records actual small-grid physical/streaming checks,
Seoul-wide same-resource benchmarks, browser pre-run/running/comparison screens,
architecture review and input/result preservation. Worker assertions alone are
not an outer review. Missing or stale review fails before any new simulation.

The outer reviewer must inspect the recorded results before creating this file;
workers leave missing review evidence as unverified, without fabricating it.
This script additionally exercises real native compare/pause/resume/save/reopen
paths. No acceptance tolerance for Reference RMSE/IoU is invented here.
"""

import json
import hashlib
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

from antiflood.history import load_depth

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = "http://127.0.0.1:8000"
CRITERIA = {f"G{i:02d}" for i in range(1, 17)}


def final_review():
    path = ROOT / ".ralph/runtime/final-review.json"
    require(path.is_file(), "G01–G16 outer review is missing; implementation alone is not completion")
    review = json.loads(path.read_text(encoding="utf8"))
    require(set(review.get("criteria", {})) == CRITERIA, "Outer review must cover G01–G16")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    sources = {name for name in tracked if name.startswith(("engine/", "src/", "web/", "docs/", "scripts/"))
               or name in ("README.md", "AGENTS.md", "pyproject.toml")}
    hashes = review.get("source_sha256", {})
    require(set(hashes) == sources, "Outer review source coverage differs")
    for name in sources:
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == hashes[name],
                f"Outer review is stale: {name}")
    for name, result in review["criteria"].items():
        require(result.get("status") == "VERIFIED" and result.get("evidence"), f"Unverified criterion: {name}")
        for value in result["evidence"]:
            evidence = (ROOT / value).resolve()
            require(evidence.is_relative_to(ROOT) and evidence.is_file(), f"Missing evidence for {name}")
    return review


def request(path, body=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(ADDRESS + path, data=data, headers={"Content-Type": "application/json"}), timeout=30) as response:
        value = response.read()
        return value if raw else json.loads(value)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    review = final_review()
    health = request("/api/health")
    require(health.get("application") == "antiflood" and all(health.get(k) for k in
            ("engine_ready", "data_ready", "replay_ready", "map_ready")), "Prepared server unavailable")
    initial = request("/api/simulation/state")
    require(initial["status"] == "ready" and initial["run_id"] is None,
            "Existing simulation state must be preserved; use an idle ready server")
    readme = (ROOT / "README.md").read_text(encoding="utf8")
    require([line for line in readme.splitlines() if line.startswith("## ")] ==
            ["## 프로젝트 주제", "## 프로젝트 동기", "## 빅데이터 알고리즘의 적용",
             "## 시스템 아키텍처", "## 리파지토리 구조"], "README sections differ")
    topic = readme.split("## 프로젝트 주제", 1)[1].split("## 프로젝트 동기", 1)[0].strip()
    require(topic == "대규모 시공간 강우 데이터가 지속적으로 유입되는 상황에서, 입력에 의해 변화하는 서울 전역의 침수 상태를 제한된 계산 자원으로 얼마나 빠르게 갱신 가능한가?",
            "Fixed research question differs")
    js = request("/assets/app.js", raw=True).decode()
    html = request("/", raw=True).decode()
    require(all(f'id="{name}"' in html for name in ("area", "drain", "threads", "boundary", "reuse", "open-run"))
            and 'el("reuse").addEventListener' in js and 'config.threads' in js, "Dashboard wiring missing")
    # The live ready server is reused; do not start or restart any server.
    pid_before = subprocess.check_output(["pgrep", "-f", "^.*python.*-m antiflood.api$"], text=True).strip()
    launch = subprocess.run(["sh", "scripts/launch.sh"], cwd=ROOT, capture_output=True, text=True, timeout=40)
    require(launch.returncode == 0 and "AntiFlood ready" in launch.stdout, "WSL launcher failed")
    require(subprocess.check_output(["pgrep", "-f", "^.*python.*-m antiflood.api$"], text=True).strip() == pid_before,
            "Launcher changed server process")
    require('wsl.exe -- sh scripts/launch.sh' in (ROOT / "Launch.cmd").read_text(), "Windows launcher wiring differs")
    settings = {"bounds": [126.999, 37.499, 127.001, 37.501], "drain_mm_h": 2, "threads": 2,
                "boundary": "closed", "drainage": "uniform"}
    region = request("/api/region", settings)
    require(region["map"]["valid_cell_count"] > 0 and region["scenarios"], "Seam region unavailable")
    west = request("/api/region", {**settings, "bounds": [126.925, 37.515, 126.927, 37.517]})
    require(west["scenarios"], "West FABDEM region unavailable")
    try:
        request("/api/region", {**settings, "threads": 0})
        raise RuntimeError("Invalid thread count accepted")
    except HTTPError as exc:
        require(exc.code == 422, "Invalid setting returned unexpected response")
    run_id = None
    owned_ids = set()
    try:
        started = request("/api/simulation/start", {**settings, "scenario_id": region["scenarios"][0]["id"],
                                                     "mode": "compare"})
        run_id = started["run_id"]
        owned_ids.add(run_id)
        paused = request("/api/simulation/pause", {})
        require(paused["status"] == "paused", "Pause failed")
        require(request("/api/simulation/resume", {})["status"] == "running", "Resume failed")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = request("/api/simulation/state")
            if state["status"] in ("completed", "error"):
                break
            time.sleep(.3)
        require(state["status"] == "completed" and state["progress"] == 1 and not state["error"],
                f"Replay did not complete: {state['status']}")
        run = request(f"/api/runs/{run_id}")
        require(run["settings"] == settings and run["frames"], "Saved settings/frames differ")
        require(run.get("reference_id"), "Reference comparison was not produced")
        frames = run["frames"]
        latest = frames[-1]
        require(latest["rain_m3"] > 0 and latest["worker_count"] == 2 and latest["cumulative_cell_updates"] > 0,
                "Real rainfall/native OpenMP work not observed")
        require(latest["drain_m3"] > 0 and latest["boundary_outflow_m3"] == 0,
                "Drainage or closed boundary result differs")
        # Inspect every generated depth grid, and the application's conservation check.
        for frame in frames:
            stem = frame["id"].rsplit("_", 1)[1]
            depth = load_depth(ROOT / "outputs/frames" / run_id, stem)
            require(np.isfinite(depth).all() and depth.min() >= 0, "Invalid depth grid")
            require(abs(frame["mass_error_m3"]) <= max(1e-7, frame["rain_m3"] * 1e-10), "Mass balance failed")
            comparison = frame.get("comparison", {})
            require(np.isfinite(comparison.get("rmse_m", np.nan)), "Reference depth RMSE missing")
            require(comparison.get("iou") is None or 0 <= comparison["iou"] <= 1, "Reference IoU invalid")
            ref = request(f"/api/frames/{frame['reference_frame_id']}/point?lon=127&lat=37.5")
            require(ref.get("time") == frame["time"], "Reference and adaptive times differ")
        request("/api/simulation/reset", {})
        require(request(f"/api/runs/{run_id}")["frames"] == frames, "Reset changed saved result")
        frame_id = latest["id"]
        require(request(f"/api/frames/{frame_id}.png", raw=True).startswith(b"\x89PNG\r\n\x1a\n"), "Frame PNG missing")
        point = request(f"/api/frames/{frame_id}/point?lon=127&lat=37.5")
        require(point["depth_m"] >= 0 and point["rain"], "Saved point lookup failed")
        reused = request("/api/simulation/start", {**run["settings"], "scenario_id": run["scenario"]["id"],
                                                    "mode": "streaming"})
        owned_ids.add(reused["run_id"])
        require(reused["run_id"] != run_id and reused["settings"] == settings, "Settings reuse failed")
        request("/api/simulation/reset", {})
        if not health["agent_ready"]:
            try:
                request("/api/agent/query", {"question": "현재 상태"})
            except HTTPError as exc:
                require(exc.code == 503, "Missing Solar key response differs")
            else:
                raise RuntimeError("Missing Solar key was not rejected")
        evidence = {"passed": sorted(CRITERIA), "run_id": run_id,
                    "bounds": settings["bounds"], "frames": len(frames), "last_frame": latest,
                    "point": point, "launcher_reused_pid": pid_before,
                    "reviewed_criteria": review["criteria"],
                    "limits": "Final review evidence plus independent small real-data HTTP comparison; no paid Solar call"}
        (ROOT / ".ralph/runtime/acceptance.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(evidence, ensure_ascii=False))
    finally:
        current = request("/api/simulation/state")
        if current["run_id"] in owned_ids:
            request("/api/simulation/reset", {})


if __name__ == "__main__":
    main()
