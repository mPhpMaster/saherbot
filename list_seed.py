"""Seed ``auto_replies`` from the ``list/`` folder (one row per file; trigger = filename)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from saherbot_db.models import AutoReply


def list_dir(project_root: Path | None = None) -> Path:
    root = project_root if project_root is not None else Path(__file__).resolve().parent
    return root / "list"


def seed_auto_replies_from_list_folder(session: Session, chat_id: int) -> int:
    """
    Create ``AutoReply`` rows from files in ``list/*`` for ``chat_id``.
    Skips triggers that already exist for this chat. Same rules as legacy ``load_lists``:
    content starting with ``-`` → text reply (body after prefix); otherwise → photo from ``list/<name>``.
    """
    base = list_dir()
    if not base.is_dir():
        return 0
    icid = int(chat_id)
    rows = list(session.scalars(select(AutoReply).where(AutoReply.chat_id == icid)).all())
    existing = {(r.trigger or "").strip().lower() for r in rows if (r.trigger or "").strip()}
    max_so_stmt = select(func.coalesce(func.max(AutoReply.sort_order), 0)).where(AutoReply.chat_id == icid)
    max_so = int(session.scalar(max_so_stmt) or 0)
    added = 0
    order = max_so
    for p in sorted(base.glob("*")):
        if not p.is_file():
            continue
        trigger = p.name
        key = trigger.strip().lower()
        if not key or key in existing:
            continue
        raw_bytes = p.read_bytes()
        is_text_dash = False
        text_body = ""
        if b"\x00" not in raw_bytes[:2048]:
            try:
                text = raw_bytes.decode("utf-8")
                st = text.strip()
                if st.startswith("-"):
                    is_text_dash = True
                    text_body = st[2:].lstrip()
            except UnicodeDecodeError:
                pass
        order += 1
        if is_text_dash and text_body:
            session.add(
                AutoReply(
                    chat_id=icid,
                    trigger=trigger,
                    response_type="text",
                    response_text=text_body,
                    photo_path=None,
                    enabled=True,
                    sort_order=order,
                )
            )
        else:
            rel = "list/" + trigger.replace("\\", "/")
            session.add(
                AutoReply(
                    chat_id=icid,
                    trigger=trigger,
                    response_type="photo",
                    response_text=None,
                    photo_path=rel,
                    enabled=True,
                    sort_order=order,
                )
            )
        existing.add(key)
        added += 1
    return added
