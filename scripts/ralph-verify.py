"""Independent, bounded acceptance run against the prepared local server (WSL)."""

import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = "http://127.0.0.1:8000"


def request(path, body=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(ADDRESS + path, data=data, headers={"Content-Type": "application/json"}), timeout=30) as response:
        value = response.read()
        return value if raw else json.loads(value)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    health = request("/api/health")
    require(health.get("application") == "antiflood" and all(health.get(k) for k in
            ("engine_ready", "data_ready", "replay_ready", "map_ready")), "Prepared server unavailable")
    initial = request("/api/simulation/state")
    require(initial["status"] == "ready" and initial["run_id"] is None,
            "Existing simulation state must be preserved; use an idle ready server")
    readme = (ROOT / "README.md").read_text(encoding="utf8")
    require([line for line in readme.splitlines() if line.startswith("## ")] ==
            ["## 프로젝트 주제", "## 프로젝트 동기", "## 시스템 아키텍처", "## 리포지토리 폴더 구조"], "README sections differ")
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
    settings = {"bounds": [126.999, 37.499, 127.001, 37.501], "drain_mm_h": 2, "threads": 2, "boundary": "closed"}
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
        started = request("/api/simulation/start", {**settings, "scenario_id": region["scenarios"][0]["id"]})
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
        frames = run["frames"]
        latest = frames[-1]
        require(latest["rain_m3"] > 0 and latest["worker_count"] == 2 and latest["cumulative_cell_updates"] > 0,
                "Real rainfall/native OpenMP work not observed")
        # Inspect every generated depth grid, and the application's conservation check.
        for frame in frames:
            stem = frame["id"].rsplit("_", 1)[1]
            depth = np.load(ROOT / "outputs/frames" / run_id / f"{stem}.npy")
            require(np.isfinite(depth).all() and depth.min() >= 0, "Invalid depth grid")
            require(abs(frame["mass_error_m3"]) <= max(1e-7, frame["rain_m3"] * 1e-10), "Mass balance failed")
        request("/api/simulation/reset", {})
        require(request(f"/api/runs/{run_id}")["frames"] == frames, "Reset changed saved result")
        frame_id = latest["id"]
        require(request(f"/api/frames/{frame_id}.png", raw=True).startswith(b"\x89PNG\r\n\x1a\n"), "Frame PNG missing")
        point = request(f"/api/frames/{frame_id}/point?lon=127&lat=37.5")
        require(point["depth_m"] >= 0 and point["rain"], "Saved point lookup failed")
        reused = request("/api/simulation/start", {**run["settings"], "scenario_id": run["scenario"]["id"]})
        owned_ids.add(reused["run_id"])
        require(reused["run_id"] != run_id and reused["settings"] == settings, "Settings reuse failed")
        request("/api/simulation/reset", {})
        if not health["agent_ready"]:
            try:
                request("/api/agent/query", {"question": "현재 상태"})
            except HTTPError as exc:
                require(exc.code == 503, "Missing Solar key response differs")
        evidence = {"passed": [f"A{i}" for i in range(1, 8)], "run_id": run_id,
                    "bounds": settings["bounds"], "frames": len(frames), "last_frame": latest,
                    "point": point, "launcher_reused_pid": pid_before,
                    "limits": "UI wiring and HTTP flow checked; no fresh browser rendering or paid Solar response asserted"}
        (ROOT / ".ralph/runtime/acceptance.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps(evidence, ensure_ascii=False))
    finally:
        current = request("/api/simulation/state")
        if current["run_id"] in owned_ids:
            request("/api/simulation/reset", {})


if __name__ == "__main__":
    main()
