"""Run or control the local web dashboard (127.0.0.1 by default)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import uvicorn

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _cfg(key: str, default: str) -> str:
    from decouple import config

    return str(config(key, default=default)).strip()


def cmd_status() -> int:
    try:
        from dashboard.process_control import dashboard_status, read_dashboard_pid
    except ImportError:
        print("Import dashboard.process_control failed; run from project root with venv activated.")
        return 2
    pid = read_dashboard_pid()
    st = dashboard_status()
    print(f"dashboard {st}" + (f" pid={pid}" if pid is not None else ""))
    return 0


def cmd_stop() -> int:
    try:
        from dashboard.process_control import stop_dashboard
    except ImportError as e:
        print(e)
        return 2
    ok, msg = stop_dashboard()
    print(msg)
    return 0 if ok else 1


def cmd_start() -> int:
    host = _cfg("DASHBOARD_HOST", "127.0.0.1")
    port = int(_cfg("DASHBOARD_PORT", "80") or "80")
    uvicorn.run(
        "dashboard.app:app",
        host=host,
        port=port,
        reload=False,
    )
    return 0


def cmd_background_start() -> int:
    """Start uvicorn in a detached child (same as `start` but non-blocking)."""
    root = Path(__file__).resolve().parent
    py = sys.executable
    script = root / "run_dashboard.py"
    kwargs: dict = {
        "cwd": str(root),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        cf = getattr(subprocess, "DETACHED_PROCESS", 0)
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            cf |= subprocess.CREATE_NO_WINDOW
        kwargs["creationflags"] = cf
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen([py, str(script), "start"], **kwargs)
    except OSError as e:
        print(f"Failed to start dashboard: {e}")
        return 1
    host = _cfg("DASHBOARD_HOST", "127.0.0.1")
    port = int(_cfg("DASHBOARD_PORT", "80") or "80")
    print(f"Dashboard start requested (background). Open http://{host}:{port}/ in your browser.")
    return 0


def cmd_toggle() -> int:
    try:
        from dashboard.process_control import dashboard_status, stop_dashboard
    except ImportError as e:
        print(e)
        return 2
    st = dashboard_status()
    if st == "running":
        ok, msg = stop_dashboard()
        print(msg)
        return 0 if ok else 1
    if st == "stale":
        ok, msg = stop_dashboard()
        print(msg)
    return cmd_background_start()


def main() -> int:
    ap = argparse.ArgumentParser(description="SaherBot dashboard server")
    ap.add_argument(
        "command",
        nargs="?",
        choices=("start", "stop", "status", "toggle"),
        default="start",
        help="start=foreground server, stop/status/toggle=process control",
    )
    ns = ap.parse_args()
    if ns.command == "start":
        return cmd_start()
    if ns.command == "stop":
        return cmd_stop()
    if ns.command == "status":
        return cmd_status()
    if ns.command == "toggle":
        return cmd_toggle()
    return cmd_start()


if __name__ == "__main__":
    raise SystemExit(main())
