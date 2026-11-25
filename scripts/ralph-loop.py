"""Run bounded, independent Codex rounds on an already isolated ralph/ branch."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RALPH = ROOT / ".ralph"
RUNTIME = RALPH / "runtime"
GUARDED = [".ralph/GOAL.md", "scripts/ralph-loop.py", "scripts/ralph-verify.py",
           "AGENTS.md", ".gitignore", ".ralph/PROMPT.md", ".ralph/STATE.md", ".ralph/HISTORY.md",
           "docs/DEVELOPMENT_SPEC.md", "docs/AUTONOMOUS_DEVELOPMENT.md"]
DESKTOP_CONTEXT = {
    "CODEX_APP_RUNTIME_CLI_PATH", "CODEX_APP_TOOLS_PIPE_PATH", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
    "CODEX_MCP_NODE_PATH", "CODEX_SESSION_ID", "CODEX_SHELL", "CODEX_TASK_WORKSPACE_VERIFYING_IDENTITY",
    "CODEX_THREAD_ID", "CODEX_TOOL_CALL_ID", "CODEX_WINDOWS_REGISTERED_CORE",
    "CODEX_WINDOWS_SANDBOX_PACKAGE_FAMILY",
}
ENVIRONMENT_FAILURES = (
    "registered Core launch requires an installed app",
    "app runtime provisioning service is unavailable",
    "Failed to create unified exec process",
)
SCHEMA = {"type": "object", "additionalProperties": False, "required": [
    "status", "summary", "changed_files", "verification", "failure_reason"], "properties": {
    "status": {"type": "string", "enum": ["CONTINUE", "DONE", "BLOCKED", "FAILED"]},
    "summary": {"type": "string"}, "changed_files": {"type": "array", "items": {"type": "string"}},
    "verification": {"type": "string"}, "failure_reason": {"type": "string"}}}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf8").strip()


def write(path, value):
    path.write_text(value, encoding="utf8")


def signatures():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in GUARDED}


def changed():
    # NUL-delimited paths also preserve spaces and non-ASCII filenames.
    tracked = git("diff", "--name-only", "-z", "HEAD").split("\0")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted(set(filter(None, tracked + untracked)))


def safe_files(paths):
    secret_name = re.compile(r"(^|/)(\.env($|\.)|auth\.json$|credentials|id_rsa|id_ed25519)|\.(pem|key|p12)$", re.I)
    secret_text = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}")
    for name in paths:
        path = ROOT / name
        if (not path.resolve().is_relative_to(ROOT) or path.is_symlink()
                or secret_name.search(name) or name.startswith(("Dataset/", "outputs/", "build/", ".git/"))):
            raise RuntimeError(f"Unsafe checkpoint path: {name}")
        if path.is_file() and (path.stat().st_size > 1_000_000 or secret_text.search(path.read_bytes())):
            raise RuntimeError(f"Large file or potential secret: {name}")


def cli_environment():
    env = {name: value for name, value in os.environ.items() if name.upper() not in DESKTOP_CONTEXT}
    if os.name == "nt":
        env["PATH"] = os.pathsep.join(
            entry for entry in env["PATH"].split(os.pathsep)
            if "\\windowsapps\\openai.codex" not in entry.lower()
        )
    return env


def run_process(command, stdin, log, timeout, env=None):
    with log.open("wb") as output:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   env=env, start_new_session=os.name != "nt")
        try:
            process.communicate(stdin.encode("utf8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
            raise RuntimeError(f"Process timed out after {timeout}s; see {log.relative_to(ROOT)}")
    return process.returncode


def verify(timeout, run_dir):
    command = ["wsl", "-d", "AntiFlood-Probe", "--", "sh", "-lc",
               '~/.venvs/antiflood/bin/python scripts/ralph-verify.py']
    if os.name != "nt":
        command = [sys.executable, "scripts/ralph-verify.py"]
    log = run_dir / "acceptance.log"
    report = RUNTIME / "acceptance.json"
    if report.exists():
        report.replace(run_dir / "previous-acceptance.json")
    code = run_process(command, "", log, timeout)
    if code:
        raise RuntimeError(f"Independent acceptance exited {code}; see {log.relative_to(ROOT)}")
    evidence = json.loads(report.read_text(encoding="utf8"))
    if set(evidence.get("passed", [])) != {f"G{i:02d}" for i in range(1, 17)}:
        raise RuntimeError("Independent acceptance did not confirm every fixed criterion")
    return evidence


def checkpoint(round_number, status, summary, verification, run_dir, branch):
    start = git("rev-parse", "HEAD")
    write(RALPH / "STATE.md", f"""# 현재 상태

- 상태: {status}
- 완료 라운드: {round_number}
- 결과: {summary}
- 검증: {verification}
- 시작 체크포인트: {start}
- 최신 체크포인트: 이 파일을 담은 HEAD (`git rev-parse HEAD`)
- 다음 행동: {('완료 조건 확인을 마쳤다.' if status == 'DONE' else '다음 독립 세션에서 가장 중요한 미완성 항목을 확인한다.')}
- 이번 실행 로그: `{run_dir.relative_to(ROOT).as_posix()}`
- 실제 복구 해시: `.ralph/runtime/checkpoints.json`. 작업 브랜치: {branch}
""")
    with (RALPH / "HISTORY.md").open("a", encoding="utf8") as history:
        history.write(f"\n## 컨트롤러 라운드 {round_number}\n\n- 시작 HEAD: {start}\n"
                      f"- 상태: {status}\n- 결과: {summary}\n- 검증: {verification}\n")
    paths = changed()
    safe_files(paths)
    # Inspect the exact explicit staging set before any remote mutation.
    print(json.dumps({"checkpoint_files": paths}, ensure_ascii=False), flush=True)
    git("add", "--", *paths)
    git("commit", "-m", f"ralph(round-{round_number}): {summary.splitlines()[0][:120]}")
    latest = git("rev-parse", "HEAD")
    record = {"status": status, "round": round_number, "latest_checkpoint": latest,
              "last_known_good": latest, "branch": branch, "push": "local"}
    write(RUNTIME / "checkpoints.json", json.dumps(record, indent=2))
    return latest


def run_round(command, prompt, result_path, run_dir, number, deadline, attempts, env, check_worker):
    for attempt in range(1, attempts + 1):
        timeout = int(deadline - time.monotonic())
        if timeout < 1:
            raise RuntimeError("Execution time limit reached")
        log = run_dir / f"round-{number}-attempt-{attempt}.log"
        result_path.unlink(missing_ok=True)
        code = run_process(command, prompt, log, timeout, env)
        check_worker()
        output = "\n".join(line for line in log.read_text(encoding="utf8", errors="replace").splitlines()
                           if line.startswith("Failed to create unified exec process:") or " ERROR codex_core::" in line)
        for problem in ENVIRONMENT_FAILURES:
            if problem in output:
                raise RuntimeError(f"{problem}; see {log.relative_to(ROOT)}. Run the standalone CLI smoke test before restarting.")
        if code == 0:
            return json.loads(result_path.read_text(encoding="utf8"))
        if changed() or attempt == attempts:
            raise RuntimeError(f"Codex exited {code}; see {log.relative_to(ROOT)}")
        print(f"Round {number}: Codex exited {code}; retrying with a fresh session", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rounds", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--round-timeout", type=int, default=900)
    parser.add_argument("--max-seconds", type=int, default=5400)
    parser.add_argument("--max-attempts", type=int, default=2, choices=range(1, 4))
    args = parser.parse_args()
    if min(args.round_timeout, args.max_seconds) < 1:
        parser.error("All limits must be positive")
    os.chdir(ROOT)
    RUNTIME.mkdir(exist_ok=True)
    lock = RUNTIME / "controller.lock"
    try:
        lock.open("x").close()
    except FileExistsError:
        raise RuntimeError("Controller lock exists; check for a running controller before removing it")
    try:
        branch = git("branch", "--show-current")
        if not branch.startswith("ralph/") or git("status", "--porcelain"):
            raise RuntimeError("Start on a clean, committed ralph/ branch")
        if "- 상태: DONE" in (RALPH / "STATE.md").read_text(encoding="utf8"):
            print("DONE: recorded completion; no new CLI round requested")
            return
        env = cli_environment()
        cli = shutil.which("codex.cmd" if os.name == "nt" else "codex", path=env.get("PATH"))
        if not cli:
            raise RuntimeError("Standalone Codex CLI missing from PATH")
        deadline = time.monotonic() + args.max_seconds
        subprocess.run([cli, "login", "status"], cwd=ROOT, env=env, check=True,
                       timeout=min(30, args.max_seconds))
        run_dir = RUNTIME / f"run-{time.time_ns()}"
        run_dir.mkdir()
        schema_path = run_dir / "schema.json"
        write(schema_path, json.dumps(SCHEMA))
        state = (RALPH / "STATE.md").read_text(encoding="utf8")
        first = int(re.search(r"^- 완료 라운드: (\d+)$", state, re.M)[1]) + 1
        print(f"Run logs: {run_dir.relative_to(ROOT)}", flush=True)
        for number in range(first, first + args.max_rounds):
            if time.monotonic() >= deadline:
                print("TIME_LIMIT: configured bound reached", flush=True)
                return
            before = git("rev-parse", "HEAD")
            guard = signatures()
            round_deadline = min(deadline, time.monotonic() + args.round_timeout)
            result_path = run_dir / f"round-{number}.json"
            prompt = (RALPH / "PROMPT.md").read_text(encoding="utf8")
            prompt += f"\n현재 라운드: {number}. 시작 HEAD: {before}.\n"
            command = [cli, "-a", "never", "exec", "-m", "gpt-6.1-sol", "-c",
                       "model_reasoning_effort=medium", "-s", "workspace-write", "--color", "never",
                       "--output-schema", str(schema_path), "-o", str(result_path), "-"]
            print(f"Round {number}: independent gpt-6.1-sol / medium", flush=True)

            def check_worker():
                if (git("rev-parse", "HEAD") != before or git("branch", "--show-current") != branch
                        or signatures() != guard):
                    raise RuntimeError("Worker changed protected controller inputs or Git checkpoint")

            result = run_round(command, prompt, result_path, run_dir, number, round_deadline,
                               args.max_attempts, env, check_worker)
            status, summary = result["status"], result["summary"].strip()
            verification = result["verification"].strip()
            if status not in ("CONTINUE", "DONE") or result["failure_reason"]:
                raise RuntimeError(f"Round {number} {status}: {result['failure_reason'] or summary}")
            paths = changed()
            if set(paths) != set(result["changed_files"]):
                raise RuntimeError("Worker report does not match actual changed files")
            safe_files(paths)
            if not summary or not verification or (status == "CONTINUE" and not paths):
                raise RuntimeError("A successful round must report its work and verification")
            git("diff", "--check", "HEAD")
            if status == "DONE":
                timeout = int(round_deadline - time.monotonic())
                if timeout < 1:
                    raise RuntimeError("No time remains for independent acceptance")
                evidence = verify(timeout, run_dir)
                verification += " / 독립 컨트롤러: " + json.dumps(evidence, ensure_ascii=False)
            latest = checkpoint(number, status, summary, verification, run_dir, branch)
            print(json.dumps({"status": status, "round": number, "last_known_good": latest}), flush=True)
            if status == "DONE":
                return
        else:
            print("MAX_ROUNDS: configured bound reached", flush=True)
    finally:
        lock.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        RUNTIME.mkdir(exist_ok=True)
        write(RUNTIME / "controller-error.json", json.dumps({"status": "FAILED", "error": str(exc)}))
        print(f"FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
