"""Self-update from the GitHub repo this install was cloned from (git pull)."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESTART_EXIT_CODE = 3
_job: dict = {"state": "idle", "log": [], "restart_needed_for_frontend": False}
_lock = threading.Lock()


def _run(cmd: list[str], cwd: Path = ROOT, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _git(*args: str, timeout: int = 60) -> str:
    res = _run(["git", *args], timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout).strip() or f"git {' '.join(args)} failed")
    return res.stdout.strip()


def _commit(line: str) -> dict:
    sha, subject, date = (line.split("|", 2) + ["", ""])[:3]
    return {"sha": sha, "subject": subject, "date": date}


def status() -> dict:
    if not shutil.which("git"):
        return {"available": False, "reason": "Git is not installed on this computer."}
    try:
        _git("rev-parse", "--is-inside-work-tree")
    except RuntimeError:
        return {"available": False, "reason": "This copy wasn't installed with git clone, so it can't update itself. Re-install with git clone (see WINDOWS_SETUP.md)."}
    try:
        remote = _git("remote", "get-url", "origin")
    except RuntimeError:
        return {"available": False, "reason": "No GitHub remote ('origin') is configured for this copy."}
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    _git("fetch", "--quiet", "origin", branch, timeout=90)
    upstream = f"origin/{branch}"
    behind = int(_git("rev-list", "--count", f"HEAD..{upstream}") or 0)
    log = _git("log", "-n", "20", "--pretty=%h|%s|%cI", f"HEAD..{upstream}")
    return {
        "available": True,
        "remote": re.sub(r"//[^@/]+@", "//", remote),
        "branch": branch,
        "current": _commit(_git("log", "-1", "--pretty=%h|%s|%cI")),
        "behind": behind,
        "new_commits": [_commit(line) for line in log.splitlines() if line],
        "local_changes": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _log(msg: str) -> None:
    _job["log"].append(msg)


def _apply_worker(loop: asyncio.AbstractEventLoop) -> None:
    try:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        _git("fetch", "--quiet", "origin", branch, timeout=90)
        changed = set(_git("diff", "--name-only", f"HEAD..origin/{branch}").splitlines())
        if not changed:
            _log("Already on the latest version.")
            _job["state"] = "done"
            return
        _log(f"Downloading {len(changed)} changed file(s)…")
        _log(_git("pull", "--ff-only", "origin", branch, timeout=180) or "Pulled.")
        req = ROOT / "backend" / "requirements-windows.txt"
        if "backend/requirements-windows.txt" in changed and req.exists():
            _log("Installing backend packages…")
            res = _run([sys.executable, "-m", "pip", "install", "-r", str(req)], timeout=600)
            _log("Backend packages updated." if res.returncode == 0 else f"pip failed: {res.stderr[-400:]}")
        yarn = shutil.which("yarn")
        front = ROOT / "frontend"
        if yarn and changed & {"frontend/package.json", "frontend/yarn.lock"}:
            _log("Installing frontend packages (can take a few minutes)…")
            res = _run([yarn, "install"], cwd=front, timeout=900)
            _log("Frontend packages updated." if res.returncode == 0 else f"yarn install failed: {res.stderr[-400:]}")
            _job["restart_needed_for_frontend"] = not (front / "build").exists()
        if yarn and (front / "build").exists() and any(f.startswith("frontend/") for f in changed):
            _log("Rebuilding the dashboard…")
            res = _run([yarn, "build"], cwd=front, timeout=900)
            _log("Dashboard rebuilt." if res.returncode == 0 else f"yarn build failed: {res.stderr[-400:]}")
        _log("Restarting the server…")
        _job["state"] = "restarting"
        loop.call_soon_threadsafe(loop.call_later, 1.5, os._exit, RESTART_EXIT_CODE)
    except Exception as exc:  # noqa: BLE001
        _log(f"Update failed: {exc}")
        _job["state"] = "failed"


def start_apply() -> dict:
    with _lock:
        if _job["state"] == "running":
            return job()
        _job.update(state="running", log=[], restart_needed_for_frontend=False)
    threading.Thread(target=_apply_worker, args=(asyncio.get_running_loop(),), daemon=True).start()
    return job()


def job() -> dict:
    return {**_job, "log": list(_job["log"])}
