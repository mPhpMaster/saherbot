#!/usr/bin/env python3
"""
SaherBot uninstall: mandatory ZIP backup under data/backups/, then remove venv.

Run from project root: python scripts/saherbot_uninstall.py
Windows: uninstall.bat
"""
from __future__ import annotations

import argparse
import os
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


_ROOT = project_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import backup_zip_util  # noqa: E402


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            out = (r.stdout or "") + (r.stderr or "")
            if "No tasks are running" in out or "no se encontraron" in out.lower():
                return False
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


def _kill_pid(pid: int) -> None:
    if not is_pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline and is_pid_alive(pid):
            time.sleep(0.2)
        if is_pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _try_stop_processes(root: Path) -> None:
    for name in ("bot.pid", "dashboard.pid"):
        p = root / "data" / name
        if not p.is_file():
            continue
        try:
            pid = int(p.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            continue
        _kill_pid(pid)
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def create_uninstall_backup(root: Path, zip_path: Path, include_env: bool) -> tuple[bool, str]:
    return backup_zip_util.create_backup_zip(
        root,
        zip_path,
        include_env=include_env,
        manifest_kind="saherbot_uninstall_backup",
    )


def _remove_venv(root: Path) -> None:
    v = root / "venv"
    if v.is_dir():
        shutil.rmtree(v, ignore_errors=True)


def _clean_data_keep_backups(root: Path) -> None:
    d = root / "data"
    if not d.is_dir():
        return
    backups = d / "backups"
    tmp_keep = root / ".uninstall_backup_keep"
    try:
        if backups.is_dir():
            if tmp_keep.exists():
                shutil.rmtree(tmp_keep, ignore_errors=True)
            shutil.move(str(backups), str(tmp_keep))
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        if tmp_keep.exists():
            shutil.move(str(tmp_keep), str(backups))
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="SaherBot uninstall with mandatory backup.")
    ap.add_argument("--yes", action="store_true", help="Skip interactive confirmation (dangerous).")
    ap.add_argument("--include-env", action="store_true", help="Include .env in backup (secrets).")
    args = ap.parse_args()

    root = project_root()
    os.chdir(root)

    if not args.yes:
        print("This will BACK UP then remove venv/ and clean data/ (keeping data/backups/).")
        a = input("Type YES to continue: ").strip()
        if a != "YES":
            print("Aborted.")
            return 1
        if not args.include_env:
            b = input("Include .env in the backup ZIP? Type YES for yes, anything else to skip: ").strip()
            if b == "YES":
                args.include_env = True

    _try_stop_processes(root)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    zip_path = root / "data" / "backups" / f"uninstall-{stamp}.zip"
    ok, msg = create_uninstall_backup(root, zip_path, args.include_env)
    if not ok:
        print(msg, file=sys.stderr)
        return 2
    print("Backup created:", msg)

    # Optional DB dump hints (URL resolved from DB_* in saherbot_db.database)
    try:
        from saherbot_db.database import resolve_database_url

        url = resolve_database_url().lower()
    except Exception:
        url = ""
    if "mysql" in url and not shutil.which("mysqldump"):
        print(
            "[WARN] Database URL points to MySQL but mysqldump not in PATH; "
            "export SQL separately if you rely on MySQL.",
            file=sys.stderr,
        )
    if "postgresql" in url and not shutil.which("pg_dump"):
        print(
            "[WARN] Database URL points to PostgreSQL but pg_dump not in PATH; "
            "export SQL separately if you rely on Postgres.",
            file=sys.stderr,
        )

    _remove_venv(root)
    _clean_data_keep_backups(root)
    print("Uninstall finished. venv removed; data reset except backups/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
