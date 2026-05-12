"""Shared ZIP backup for SaherBot (SQLite DB, list/, optional .env)."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def add_tree(z: zipfile.ZipFile, src_dir: Path, arc_prefix: str) -> list[str]:
    files: list[str] = []
    if not src_dir.is_dir():
        return files
    for path in src_dir.rglob("*"):
        if path.is_file():
            archive_name = arc_prefix + str(path.relative_to(src_dir)).replace("\\", "/")
            z.write(path, archive_name)
            files.append(archive_name)
    return files


def create_backup_zip(
    root: Path,
    zip_path: Path,
    *,
    include_env: bool,
    manifest_kind: str,
) -> tuple[bool, str]:
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"Cannot create backups folder: {e}"

    manifest = {
        "kind": manifest_kind,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            db = root / "data" / "saherbot.db"
            if db.is_file():
                z.write(db, "data/saherbot.db")
                manifest["files"].append("data/saherbot.db")
            manifest["files"].extend(add_tree(z, root / "list", "list/"))
            if include_env:
                envf = root / ".env"
                if envf.is_file():
                    z.write(envf, ".env")
                    manifest["files"].append(".env")
            manifest["files"].append("manifest.json")
            z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    except Exception as e:
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"Backup failed: {e}"
    return True, str(zip_path)


def _restore_member_target(root: Path, member_name: str) -> Path | None:
    normalized = member_name.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if not parts or normalized.startswith("/") or ".." in parts:
        return None
    if normalized == "data/saherbot.db":
        return root / "data" / "saherbot.db"
    if normalized.startswith("list/") and not normalized.endswith("/"):
        return root / normalized
    return None


def restore_from_zip(root: Path, zip_path: Path) -> tuple[bool, str]:
    """Restore SQLite DB and list/ files from a trusted backup ZIP, rejecting unsafe paths."""
    if not zip_path.is_file():
        return False, "Backup ZIP not found."
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            try:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            except KeyError:
                return False, "manifest.json is missing from the backup."
            except json.JSONDecodeError:
                return False, "manifest.json is invalid."
            manifest_files = set(manifest.get("files") or [])
            if "data/saherbot.db" not in manifest_files and not any(str(x).startswith("list/") for x in manifest_files):
                return False, "Manifest does not list restorable data."
            members = []
            for info in z.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/")
                if normalized == "manifest.json":
                    continue
                if normalized not in manifest_files:
                    return False, "ZIP contains a file not listed in manifest: " + info.filename
                target = _restore_member_target(root, info.filename)
                if target is None:
                    continue
                try:
                    target.resolve().relative_to(root.resolve())
                except ValueError:
                    return False, "Unsafe path in backup: " + info.filename
                members.append((info, target))
            if not members:
                return False, "No restorable data/saherbot.db or list/ files found."

            if any(info.filename.replace("\\", "/").startswith("list/") for info, _target in members):
                list_dir = root / "list"
                if list_dir.is_dir():
                    shutil.rmtree(list_dir)
                list_dir.mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir(parents=True, exist_ok=True)
            db = root / "data" / "saherbot.db"
            if db.is_file() and any(info.filename.replace("\\", "/") == "data/saherbot.db" for info, _target in members):
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                shutil.copy2(db, root / "data" / f"saherbot.db.bak-{stamp}")

            restored = 0
            for info, target in members:
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info, "r") as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                restored += 1
    except zipfile.BadZipFile:
        return False, "Invalid ZIP file."
    except Exception as e:
        return False, "Restore failed: " + str(e)
    return True, f"{restored} file(s) restored from {zip_path.name}."
