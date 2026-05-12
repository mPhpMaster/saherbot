"""Runtime config from DB for the bot (monitored chats revision, events, etc.)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from saherbot_db.bootstrap import bump_chats_revision, init_db
from saherbot_db.database import get_session_factory
from saherbot_db.models import AutoReply, Bot, Chat, ChatBannedWord, Event, GlobalSettings

_lock = threading.RLock()
_cached_revision: int = -1
# chat_id -> (bot_id, moderation_enabled); explicit bot_id from DB, or sole-token bot for orphan chats
_cached_chat_meta: dict[int, tuple[int, bool]] = {}
# Banned words: invalidated when ``chats_config_revision`` changes (dashboard bumps on CRUD) or TTL ~60s per chat.
_banned_words_cache_rev: int = -999
_banned_words_cache: dict[int, tuple[float, list[str]]] = {}
_BANNED_WORDS_TTL_SEC = 60.0


def ensure_db() -> None:
    init_db()


def _sole_bot_id_with_token(session: Session) -> Optional[int]:
    """If exactly one dashboard bot has a non-empty token, return its id; else None."""
    bots = list(session.scalars(select(Bot).order_by(Bot.id)).all())
    with_token = [b for b in bots if (b.bot_token or "").strip()]
    if len(with_token) != 1:
        return None
    return int(with_token[0].id)


def _reload_monitored_locked(session: Session) -> dict[int, tuple[int, bool]]:
    global _cached_revision, _cached_chat_meta
    gs = session.get(GlobalSettings, 1)
    rev = int(gs.chats_config_revision) if gs else 0
    rows = session.execute(
        select(Chat.chat_id, Chat.bot_id, Chat.moderation_enabled).where(Chat.bot_id.isnot(None))
    ).all()
    _cached_revision = rev
    meta: dict[int, tuple[int, bool]] = {}
    for cid, bid, mod in rows:
        if bid is None:
            continue
        ib = int(bid)
        if ib > 0:
            meta[int(cid)] = (ib, bool(mod))
    sole = _sole_bot_id_with_token(session)
    if sole is not None:
        for c in session.scalars(select(Chat).where(Chat.bot_id.is_(None))).all():
            icid = int(c.chat_id)
            if icid not in meta:
                meta[icid] = (sole, bool(c.moderation_enabled))
    _cached_chat_meta = meta
    try:
        import logger

        keys = sorted(meta.keys())
        preview = keys[:30]
        tail = " …" if len(keys) > 30 else ""
        logger.log(
            f"config_store: monitored map rev={rev} count={len(keys)} chat_ids={preview}{tail}",
            "info",
        )
    except Exception:
        pass
    return _cached_chat_meta


def monitored_chat_ids_for_bot_id(bot_id: int) -> list[int]:
    """Chat IDs in the in-memory map assigned to this dashboard bot (after refresh)."""
    refresh_monitored_if_needed()
    bid = int(bot_id)
    with _lock:
        return sorted(cid for cid, (b, _) in _cached_chat_meta.items() if int(b) == bid)


def bootstrap_monitored_cache_from_db() -> None:
    """Force-reload monitored-chat map from DB (call after ``set_bot_context`` in each bot thread)."""
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        with _lock:
            _reload_monitored_locked(session)


def refresh_monitored_if_needed() -> None:
    """Call from bot message path: reload monitored set when chats_config_revision changes."""
    global _cached_revision
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        gs = session.get(GlobalSettings, 1)
        if gs is None:
            return
        rev = int(gs.chats_config_revision)
        with _lock:
            if rev != _cached_revision:
                _reload_monitored_locked(session)


def is_chat_assigned_to_current_bot(chat_id: int) -> bool:
    """True if this chat is linked to the current bot thread in the dashboard (any moderation flag)."""
    refresh_monitored_if_needed()
    try:
        import bot_context

        cur_bid = int(bot_context.get_bot_id())
    except Exception:
        return False
    if cur_bid <= 0:
        return False
    icid = int(chat_id)
    with _lock:
        tup = _cached_chat_meta.get(icid)
        return tup is not None and int(tup[0]) == cur_bid


def is_chat_monitored_use_dashboard(chat_id: int) -> bool:
    """True if chat is linked to this bot and moderation is enabled (delete/limit/banned-word rules apply)."""
    refresh_monitored_if_needed()
    try:
        import bot_context

        cur_bid = int(bot_context.get_bot_id())
    except Exception:
        return False
    if cur_bid <= 0:
        return False
    icid = int(chat_id)
    with _lock:
        tup = _cached_chat_meta.get(icid)
        return tup is not None and int(tup[0]) == cur_bid and bool(tup[1])


def log_event(
    event_type: str,
    chat_id: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    try:
        SessionLocal = get_session_factory()
        with SessionLocal() as session:
            session.add(Event(event_type=event_type, chat_id=chat_id, meta_json=meta or {}))
            session.commit()
    except Exception:
        pass


def get_primary_chat_id_for_bot(bot_id: int) -> Optional[int]:
    """Primary / admin lookup group for this bot (private /id flows, is_admin without chat)."""
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        b = session.get(Bot, int(bot_id))
        if b is None:
            return None
        pid = int(b.primary_chat_id or 0)
        return pid if pid else None


_DEFAULT_MSG_MAX_LENGTH = 300
# أنواع محتوى افتراضية (كانت في loader.ALLOWED_TYPES) عندما لا يوجد JSON في المحادثة
DEFAULT_ALLOWED_CONTENT_TYPES: tuple[str, ...] = ("audio", "photo", "voice", "video", "text")


def get_effective_chat_settings(chat_id: int) -> dict[str, Any]:
    """Length / echo limits come from the ``chats`` row only (per monitored chat)."""
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        chat = session.get(Chat, int(chat_id))
        if chat is None:
            return {
                "msg_max_length": _DEFAULT_MSG_MAX_LENGTH,
                "msg_length_unlimited": False,
                "echo_enabled": False,
                "moderation_apply_to_admins": False,
                "moderation_block_phones": False,
                "moderation_block_mentions": False,
                "moderation_block_links": False,
                "allowed_content_types": list(DEFAULT_ALLOWED_CONTENT_TYPES),
            }
        msg_max_length = chat.msg_max_length if chat.msg_max_length is not None else _DEFAULT_MSG_MAX_LENGTH
        msg_length_unlimited = bool(chat.msg_length_unlimited)
        echo_enabled = bool(chat.echo_enabled) if chat.echo_enabled is not None else False
        apply_admins = bool(getattr(chat, "moderation_apply_to_admins", False))
        block_phones = bool(getattr(chat, "moderation_block_phones", True))
        block_mentions = bool(getattr(chat, "moderation_block_mentions", True))
        block_links = bool(getattr(chat, "moderation_block_links", True))
        raw_allowed = getattr(chat, "allowed_content_types", None)
        allowed_ct: list[str] = []
        if isinstance(raw_allowed, list):
            allowed_ct = [str(x).strip() for x in raw_allowed if str(x).strip()]
        if not allowed_ct:
            allowed_ct = list(DEFAULT_ALLOWED_CONTENT_TYPES)
        return {
            "msg_max_length": msg_max_length,
            "msg_length_unlimited": msg_length_unlimited,
            "echo_enabled": echo_enabled,
            "moderation_apply_to_admins": apply_admins,
            "moderation_block_phones": block_phones,
            "moderation_block_mentions": block_mentions,
            "moderation_block_links": block_links,
            "allowed_content_types": allowed_ct,
        }


def get_banned_words_lower_for_chat(chat_id: int) -> list[str]:
    """Lowercased forbidden substrings for ``chat_id`` (cached; refresh on revision bump or TTL)."""
    global _banned_words_cache_rev, _banned_words_cache
    refresh_monitored_if_needed()
    icid = int(chat_id)
    tmono = time.monotonic()
    with _lock:
        rev = _cached_revision
        if rev != _banned_words_cache_rev:
            _banned_words_cache.clear()
            _banned_words_cache_rev = rev
        hit = _banned_words_cache.get(icid)
        if hit is not None and (tmono - hit[0]) < _BANNED_WORDS_TTL_SEC:
            return hit[1]
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        rows = session.scalars(
            select(ChatBannedWord.word).where(ChatBannedWord.chat_id == icid).order_by(ChatBannedWord.id)
        ).all()
    words = [str(w).strip() for w in rows if w and str(w).strip()]
    with _lock:
        _banned_words_cache[icid] = (time.monotonic(), words)
    return words


def list_auto_reply_triggers_for_chat(chat_id: int) -> list[str]:
    """Trigger strings for this chat (for ``/help``), same order as matching: sort_order, id."""
    icid = int(chat_id)
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        rows = session.scalars(
            select(AutoReply.trigger)
            .where(AutoReply.chat_id == icid)
            .order_by(AutoReply.sort_order, AutoReply.id)
        ).all()
    out: list[str] = []
    for t in rows:
        s = (str(t).strip() if t is not None else "")
        if s:
            out.append(s)
    return out


def find_auto_reply(chat_id: int, text: str) -> tuple[Any, str] | None:
    """Find enabled DB auto-reply for this chat only (no global scope)."""
    needle = (text or "").strip().lower()
    if not needle:
        return None
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        rows = session.scalars(
            select(AutoReply)
            .where(AutoReply.chat_id == int(chat_id))
            .where(AutoReply.enabled.is_(True))
            .order_by(AutoReply.sort_order, AutoReply.id)
        ).all()
        for row in rows:
            trigger = (row.trigger or "").strip()
            if trigger.lower() != needle:
                continue
            if row.response_type == "photo" and row.photo_path:
                path = Path(row.photo_path)
                if not path.is_absolute():
                    path = Path(__file__).resolve().parent / path
                if path.is_file():
                    return {"path": str(path)}, trigger
                continue
            if row.response_text:
                return row.response_text, trigger
    return None
