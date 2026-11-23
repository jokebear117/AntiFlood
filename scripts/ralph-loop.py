"""Run bounded, independent Codex rounds on an already isolated ralph/ branch."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RALPH = ROOT / ".ralph"
RUNTIME = RALPH / "runtime"
GUARDED = [".ralph/GOAL.md", "scripts/ralph-loop.py", "scripts/ralph-verify.py",
           "AGENTS.md", ".gitignore"]
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


def run_process(command, stdin, log, timeout):
    with log.open("wb") as output:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                                   stdout=output, stderr=subprocess.STDOUT)
        try:
            process.communicate(stdin.encode("utf8"), timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.kill()
            process.wait()
            raise RuntimeError(f"Process timed out after {timeout}s; see {log.relative_to(ROOT)}")
    return process.returncode


def verify(timeout):
    command = ["wsl", "-d", "AntiFlood-Probe", "--", "sh", "-lc",
               '~/.venvs/antiflood/bin/python scripts/ralph-verify.py']
    if os.name != "nt":
        command = [sys.executable, "scripts/ralph-verify.py"]
    log = RUNTIME / "acceptance.log"
    (RUNTIME / "acceptance.json").unlink(missing_ok=True)
    code = run_process(command, "", log, timeout)
    if code:
        raise RuntimeError(f"Independent acceptance exited {code}; see .ralph/runtime/acceptance.log")
    evidence = json.loads((RUNTIME / "acceptance.json").read_text(encoding="utf8"))
    if set(evidence.get("passed", [])) != {f"A{i}" for i in range(1, 8)}:
        raise RuntimeError("Independent acceptance did not confirm every fixed criterion")
    return evidence


def checkpoint(round_number, status, summary, verification, last_good, branch):
    start = git("rev-parse", "HEAD")
    write(RALPH / "STATE.md", f"""# 현재 상태

- 상태: {status}
- 완료 라운드: {round_number}
- 결과: {summary}
- 검증: {verification}
- 시작 체크포인트: {start}
- 최신 체크포인트: 이 파일을 담은 HEAD (`git rev-parse HEAD`)
- 마지막 정상 커밋: {('HEAD (독립 완료 검증 통과)' if status == 'DONE' else last_good)}
- 다음 행동: {('완료. 추가 제품 작업 없이 종료.' if status == 'DONE' else '아래 이력의 장애물과 남은 완료 조건을 확인한다.')}
- 실제 복구 해시·푸시 결과: `.ralph/runtime/checkpoints.json`. 원격 전용 브랜치: {branch}
""")
    with (RALPH / "HISTORY.md").open("a", encoding="utf8") as history:
        history.write(f"\n## 컨트롤러 라운드 {round_number}\n\n- 시작 HEAD: {start}\n"
                      f"- 상태: {status}\n- 결과: {summary}\n- 검증: {verification}\n")
    paths = changed()
    safe_files(paths)
    # Inspect the exact explicit staging set before any remote mutation.
    print(json.dumps({"checkpoint_files": paths}, ensure_ascii=False), flush=True)
    git("add", "--", *paths)
    prefix = "ralph" if status == "DONE" else "ralph-wip"
    git("commit", "-m", f"{prefix}(round-{round_number}): {status.lower()} completion checkpoint")
    latest = git("rev-parse", "HEAD")
    if status == "DONE":
        last_good = latest
    record = {"status": status, "round": round_number, "latest_checkpoint": latest,
              "last_known_good": last_good, "branch": branch, "push": "pending"}
    write(RUNTIME / "checkpoints.json", json.dumps(record, indent=2))
    try:
        git("push", "--set-upstream", "origin", f"HEAD:refs/heads/{branch}")
        if git("ls-remote", "--heads", "origin", branch).split()[0] != latest:
            raise RuntimeError("Remote checkpoint does not match local HEAD")
    except Exception:
        record.update(status="FAILED", push="failed")
        write(RUNTIME / "checkpoints.json", json.dumps(record, indent=2))
        raise
    record["push"] = "success"
    write(RUNTIME / "checkpoints.json", json.dumps(record, indent=2))
    return last_good


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rounds", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--round-timeout", type=int, default=900)
    parser.add_argument("--no-progress-limit", type=int, default=2)
    parser.add_argument("--same-failure-limit", type=int, default=2)
    args = parser.parse_args()
    if min(args.round_timeout, args.no_progress_limit, args.same_failure_limit) < 1:
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
        git("ls-remote", "--heads", "origin", branch)
        cli = shutil.which("codex.cmd" if os.name == "nt" else "codex")
        if not cli:
            raise RuntimeError("Codex CLI missing")
        subprocess.run([cli, "login", "status"], cwd=ROOT, check=True)
        write(RUNTIME / "schema.json", json.dumps(SCHEMA))
        guard = signatures()
        last_good = "21f4d5387884653867edea2358dde9b18cedc49b"
        journal = RUNTIME / "checkpoints.json"
        first = 1
        if journal.exists():
            prior = json.loads(journal.read_text(encoding="utf8"))
            if prior["latest_checkpoint"] != git("rev-parse", "HEAD") or prior["push"] != "success":
                raise RuntimeError("Resolve prior checkpoint/push failure before restarting")
            last_good, first = prior["last_known_good"], prior["round"] + 1
        no_progress = same_failure = 0
        previous_failure = ""
        status = "MAX_ROUNDS"
        for number in range(first, args.max_rounds + 1):
            before = git("rev-parse", "HEAD")
            started = time.monotonic()
            result_path = RUNTIME / f"round-{number}.json"
            prompt = (RALPH / "PROMPT.md").read_text(encoding="utf8")
            prompt += f"\n현재 라운드: {number}. 시작 HEAD: {before}.\n"
            command = [cli, "-a", "never", "exec", "-m", "gpt-6.1-sol", "-c",
                       "model_reasoning_effort=medium", "-s", "workspace-write", "--color", "never",
                       "--output-schema", str(RUNTIME / "schema.json"), "-o", str(result_path), "-"]
            print(f"Round {number}: independent gpt-6.1-sol / medium", flush=True)
            verification = "검증 미실행"
            try:
                code = run_process(command, prompt, RUNTIME / f"round-{number}.log", args.round_timeout)
                if code:
                    raise RuntimeError(f"Codex exited {code}; see round-{number}.log")
                if git("rev-parse", "HEAD") != before or git("branch", "--show-current") != branch or signatures() != guard:
                    raise RuntimeError("Worker changed protected controller inputs or Git checkpoint")
                result = json.loads(result_path.read_text(encoding="utf8"))
                if set(result) != set(SCHEMA["required"]) or result["status"] not in SCHEMA["properties"]["status"]["enum"]:
                    raise RuntimeError("Invalid round response")
                status, summary = result["status"], result["summary"]
                allowed = set(result["changed_files"]) | {".ralph/STATE.md", ".ralph/HISTORY.md"}
                if not set(changed()) <= allowed:
                    raise RuntimeError("Undeclared worker changes; inspect before checkpoint")
                verification = result["verification"]
                if status == "DONE":
                    evidence = verify(max(1, args.round_timeout - int(time.monotonic() - started)))
                    verification += " / 독립 컨트롤러: " + json.dumps(evidence, ensure_ascii=False)
                failure = result["failure_reason"]
                same_failure = same_failure + 1 if failure and failure == previous_failure else int(bool(failure))
                previous_failure = failure
                product_changes = [p for p in changed() if not p.startswith(".ralph/")]
                no_progress = 0 if product_changes else no_progress + 1
                if status == "CONTINUE" and (no_progress >= args.no_progress_limit or same_failure >= args.same_failure_limit):
                    status, summary = "BLOCKED", summary + " / 무진전 또는 동일 실패 제한 도달"
                if status == "CONTINUE" and number == args.max_rounds:
                    status = "MAX_ROUNDS"
            except Exception as exc:
                status, summary = "FAILED", str(exc)
                verification += " / 독립 검증 실패 또는 실행 제어 오류; 성공으로 취급하지 않음"
            # Safety violations preserve the tree for inspection, without staging/pushing it.
            if git("rev-parse", "HEAD") != before or git("branch", "--show-current") != branch or signatures() != guard:
                raise RuntimeError(summary)
            last_good = checkpoint(number, status, summary, verification, last_good, branch)
            print(json.dumps({"status": status, "round": number, "last_known_good": last_good}), flush=True)
            if status in ("DONE", "BLOCKED", "FAILED"):
                break
        else:
            print("MAX_ROUNDS: configured bound reached", flush=True)
        if status in ("BLOCKED", "FAILED"):
            raise SystemExit(1)
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
