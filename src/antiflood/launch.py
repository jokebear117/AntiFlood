"""Start the prepared local server and wait until the dashboard can be opened."""

import json
import os
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError

from .data import ROOT


def main():
    address = "http://127.0.0.1:8000/api/health"

    def health():
        try:
            with urlopen(address, timeout=2) as response:
                return json.load(response)
        except (URLError, ValueError, TimeoutError):
            return None

    state = health()
    process = None
    if state is None:
        log_dir = ROOT / "outputs/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "launcher.log").open("ab") as output:
            environment = dict(os.environ, ANTIFLOOD_PORT="8000")
            process = subprocess.Popen(
                [sys.executable, "-m", "antiflood.api"], cwd=ROOT, env=environment,
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True,
            )
        for _ in range(60):
            state = health()
            if state or process.poll() is not None:
                break
            time.sleep(.5)
    if state and state.get("application") == "antiflood" and state.get("replay_ready") and state.get("map_ready"):
        print("AntiFlood ready at http://127.0.0.1:8000")
        return
    if process is not None and process.poll() is None:
        process.terminate()
    if state and state.get("error"):
        print(state["error"])
    else:
        print("Cannot open AntiFlood. Port 8000 may be occupied. Check outputs/logs/launcher.log and docs/RUNNING.md.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
