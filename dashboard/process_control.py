"""Start/stop/restart the bot process on the same machine (Windows + POSIX).

- **Windows:** OpenProcess for PID checks; taskkill /T /F to stop; CREATE_NO_WINDOW for spawned bot.
- **Linux / macOS / other POSIX:** os.kill(pid, 0) for checks; SIGTERM then SIGKILL if needed;
  bot child uses ``start_new_session=True`` so it is detached like a background service.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def pid_file() -> Path:
    return project_root() / "data" / "bot.pid"


def is_pid_alive(pid: int) -> bool:
    """Whether process `pid` exists (Windows: OpenProcess; POSIX: kill 0)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        # tasklist output is locale-dependent; OpenProcess is reliable for our own PIDs.
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        # Brief retries: right after spawn, a single OpenProcess(false negative) was seen on some systems.
        for attempt in range(4):
            kernel32.SetLastError(0)
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            err = ctypes.get_last_error()
            # 5 = ERROR_ACCESS_DENIED — process exists but we cannot open it
            if err == 5:
                return True
            if attempt < 3:
                time.sleep(0.06)
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _python_for_bot() -> str:
    """Prefer project venv so the bot uses the same deps as install, not a random PATH python."""
    root = project_root()
    if os.name == "nt":
        cand = root / "venv" / "Scripts" / "python.exe"
        if cand.is_file():
            return str(cand)
    else:
        for rel in ("venv/bin/python3", "venv/bin/python"):
            cand = root / rel
            if cand.is_file():
                return str(cand)
    return sys.executable


def read_bot_pid() -> int | None:
    p = pid_file()
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def prune_stale_bot_pid() -> None:
    """If ``data/bot.pid`` references a dead process, remove it (fixes stuck 'stale' after crashes)."""
    pid = read_bot_pid()
    if pid is None:
        return
    if not is_pid_alive(pid):
        try:
            pid_file().unlink(missing_ok=True)
        except OSError:
            pass


def bot_status() -> str:
    pid = read_bot_pid()
    if pid is None:
        return "stopped"
    if is_pid_alive(pid):
        return "running"
    return "stale"


def _tail_file_lines(path: Path, max_lines: int, chunk_size: int = 65536) -> list[str]:
    """Last ``max_lines`` lines from a file (UTF-8, ignore errors)."""
    blocks: list[bytes] = []
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            newline_count = 0
            while pos > 0 and newline_count < max_lines + 1:
                step = min(chunk_size, pos)
                pos -= step
                f.seek(pos)
                blocks.insert(0, f.read(step))
                newline_count = b"".join(blocks).count(b"\n")
    except OSError:
        return []
    text = b"".join(blocks).decode("utf-8", errors="ignore")
    lines = text.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def tail_log_snippet(path: Path, *, max_lines: int = 3, max_chars: int = 500) -> str:
    """Non-empty tail of a log file, truncated to ``max_chars`` (from the end if needed)."""
    if not path.is_file():
        return ""
    lines = _tail_file_lines(path, max_lines)
    text = "\n".join(lines).strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = "…" + text[-(max_chars - 1) :]
    return text


def _spawn_log_excerpt(*, max_lines: int = 3, max_chars: int = 420) -> str:
    """Single-line-ish excerpt from bot-spawn.log for error messages."""
    raw = tail_log_snippet(project_root() / "logs" / "bot-spawn.log", max_lines=max_lines, max_chars=max_chars + 80)
    if not raw:
        return ""
    one = " ".join(raw.split())
    if len(one) > max_chars:
        one = "…" + one[-(max_chars - 1) :]
    return one


def bot_status_last_message(*, max_lines: int = 3, max_chars: int = 500) -> str:
    """Brief recent log text for dashboard status hover: spawn log, else today's app log."""
    root = project_root()
    spawn = root / "logs" / "bot-spawn.log"
    s = tail_log_snippet(spawn, max_lines=max_lines, max_chars=max_chars)
    if s:
        return s
    daily = root / "logs" / (time.strftime("%d-%m-%Y") + ".log")
    return tail_log_snippet(daily, max_lines=max_lines, max_chars=max_chars)


def _start_fail_message(prefix: str) -> str:
    ex = _spawn_log_excerpt()
    if ex:
        return f"{prefix} Details: {ex}"
    return prefix


def start_bot() -> tuple[bool, str]:
    pid = read_bot_pid()
    if pid is not None:
        if is_pid_alive(pid):
            return False, "Bot is already running."
        try:
            pid_file().unlink(missing_ok=True)
        except OSError:
            pass
    root = project_root()
    main_py = root / "main.py"
    if not main_py.is_file():
        return False, "main.py not found."
    py = _python_for_bot()
    kwargs: dict = {"cwd": str(root)}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        # Detach from the dashboard's tty / process group (similar intent to no console on Windows).
        kwargs["start_new_session"] = True

    log_path = root / "logs" / "bot-spawn.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "a", encoding="utf-8", buffering=1)
    try:
        log_f.write(f"\n--- bot spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        log_f.flush()
        kwargs["stdout"] = log_f
        kwargs["stderr"] = subprocess.STDOUT
        proc = subprocess.Popen([py, str(main_py)], **kwargs)
    except OSError as e:
        return False, f"Failed to start bot process: {e}"
    finally:
        try:
            log_f.close()
        except OSError:
            pass

    # Let stop/status work before main.py finishes heavy imports; child overwrites with same PID in startBot().
    try:
        pid_file().parent.mkdir(parents=True, exist_ok=True)
        pid_file().write_text(str(proc.pid), encoding="utf-8")
    except OSError:
        pass

    time.sleep(1.0)
    if proc.poll() is not None:
        try:
            pid_file().unlink(missing_ok=True)
        except OSError:
            pass
        return (
            False,
            _start_fail_message("Bot process exited immediately after start."),
        )
    if not is_pid_alive(proc.pid):
        try:
            pid_file().unlink(missing_ok=True)
        except OSError:
            pass
        return (
            False,
            _start_fail_message("Bot process not found after start (process ended)."),
        )
    # Extra window: child can still exit during heavy imports after the first check.
    for _ in range(4):
        time.sleep(0.2)
        if proc.poll() is not None or not is_pid_alive(proc.pid):
            try:
                pid_file().unlink(missing_ok=True)
            except OSError:
                pass
            return (
                False,
                _start_fail_message("Bot process exited shortly after start."),
            )
    return True, "Start command sent."


def stop_bot(wait_sec: float = 8.0) -> tuple[bool, str]:
    pid = read_bot_pid()
    if pid is None:
        return True, "No PID file."
    if not is_pid_alive(pid):
        try:
            pid_file().unlink(missing_ok=True)
        except OSError:
            pass
        return True, "Process not found; PID file removed."

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as e:
        return False, f"Failed to stop bot: {e}"

    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if not is_pid_alive(pid):
            break
        time.sleep(0.2)

    if is_pid_alive(pid):
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
            except OSError:
                pass
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.5)
        deadline2 = time.monotonic() + 4.0
        while time.monotonic() < deadline2:
            if not is_pid_alive(pid):
                break
            time.sleep(0.15)

    if is_pid_alive(pid):
        return False, "Process still running after timeout."

    try:
        pid_file().unlink(missing_ok=True)
    except OSError:
        pass
    return True, "Bot stopped."


def dashboard_pid_file() -> Path:
    return project_root() / "data" / "dashboard.pid"


def read_dashboard_pid() -> int | None:
    p = dashboard_pid_file()
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def dashboard_status() -> str:
    pid = read_dashboard_pid()
    if pid is None:
        return "stopped"
    if is_pid_alive(pid):
        return "running"
    return "stale"


def stop_dashboard(wait_sec: float = 8.0) -> tuple[bool, str]:
    pid = read_dashboard_pid()
    p = dashboard_pid_file()
    if pid is None:
        return True, "No dashboard PID file."
    if not is_pid_alive(pid):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
        return True, "Dashboard process not found; removed stale PID file."
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as e:
        return False, f"Failed to stop dashboard: {e}"
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        if not is_pid_alive(pid):
            break
        time.sleep(0.2)

    if is_pid_alive(pid):
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
            except OSError:
                pass
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.5)
        deadline2 = time.monotonic() + 4.0
        while time.monotonic() < deadline2:
            if not is_pid_alive(pid):
                break
            time.sleep(0.15)

    if is_pid_alive(pid):
        return False, "Dashboard still running after timeout."

    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
    return True, "Dashboard stopped."


def restart_bot() -> tuple[bool, str]:
    ok, msg = stop_bot()
    if not ok:
        return ok, msg
    time.sleep(2)
    return start_bot()
