"""Create tables and seed default global row (first run)."""

from __future__ import annotations

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from saherbot_db.database import get_engine, get_session_factory
from saherbot_db.models import Base, Bot, Chat, ChatBannedWord, GlobalSettings


def _migrate_global_settings_columns(engine) -> None:
    try:
        insp = inspect(engine)
        if "global_settings" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("global_settings")}
        if "bot_token" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE global_settings ADD COLUMN bot_token TEXT"))
    except Exception:
        pass


def _migrate_bots_and_chat_bot_id(engine) -> None:
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "bots" not in tables:
            Bot.__table__.create(engine, checkfirst=True)
        insp2 = inspect(engine)
        if "chats" in insp2.get_table_names():
            cols = {c["name"] for c in insp2.get_columns("chats")}
            if "bot_id" not in cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE chats ADD COLUMN bot_id INTEGER"))
    except Exception:
        pass
    try:
        _migrate_legacy_token_to_bots()
    except Exception:
        pass


def _migrate_legacy_token_to_bots() -> None:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        existing = int(session.scalar(select(func.count()).select_from(Bot)) or 0)
        if existing > 0:
            return
        gs = session.get(GlobalSettings, 1)
        tok = (str(getattr(gs, "bot_token", None) or "").strip()) if gs else ""
        if not tok:
            return
        b = Bot(
            name="البوت الافتراضي",
            bot_token=tok,
            notify_on_startup=bool(getattr(gs, "notify_on_startup", False)) if gs else False,
            primary_chat_id=int(getattr(gs, "primary_chat_id", 0) or 0) if gs else 0,
        )
        session.add(b)
        session.flush()
        bid = int(b.id)
        for row in session.scalars(select(Chat)).all():
            if getattr(row, "bot_id", None) is None:
                row.bot_id = bid
        if gs:
            gs.bot_token = None
        session.commit()


def _migrate_auto_replies_chat_id(engine) -> None:
    """Legacy global rows (chat_id NULL): attach to smallest existing chat_id, else drop."""
    try:
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        if "auto_replies" not in tables:
            return
        cols = {c["name"] for c in insp.get_columns("auto_replies")}
        if "chat_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE auto_replies ADD COLUMN chat_id BIGINT"))
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE auto_replies SET chat_id = (SELECT MIN(chat_id) FROM chats) "
                    "WHERE chat_id IS NULL AND EXISTS (SELECT 1 FROM chats)"
                )
            )
            conn.execute(text("DELETE FROM auto_replies WHERE chat_id IS NULL"))
    except Exception:
        pass


def _migrate_chat_moderation_apply_to_admins(engine) -> None:
    """Per-chat: when True, group admins are moderated like regular members."""
    try:
        insp = inspect(engine)
        if "chats" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("chats")}
        if "moderation_apply_to_admins" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE chats ADD COLUMN moderation_apply_to_admins "
                        "BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
    except Exception:
        pass


def _migrate_chat_content_filter_columns(engine) -> None:
    """Per-chat: block phone numbers, @mentions, links (text + Telegram entities)."""
    try:
        insp = inspect(engine)
        if "chats" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("chats")}
        with engine.begin() as conn:
            if "moderation_block_phones" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE chats ADD COLUMN moderation_block_phones "
                        "BOOLEAN NOT NULL DEFAULT 1"
                    )
                )
            if "moderation_block_mentions" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE chats ADD COLUMN moderation_block_mentions "
                        "BOOLEAN NOT NULL DEFAULT 1"
                    )
                )
            if "moderation_block_links" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE chats ADD COLUMN moderation_block_links "
                        "BOOLEAN NOT NULL DEFAULT 1"
                    )
                )
    except Exception:
        pass


def _migrate_chat_allowed_content_types(engine) -> None:
    """Per-chat JSON list of TeleBot ``content_type`` strings allowed (else default five types)."""
    try:
        insp = inspect(engine)
        if "chats" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("chats")}
        if "allowed_content_types" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE chats ADD COLUMN allowed_content_types JSON"))
    except Exception:
        pass


def _migrate_chat_banned_words_table(engine) -> None:
    """Create ``chat_banned_words`` on existing installs (create_all is idempotent)."""
    try:
        insp = inspect(engine)
        if "chat_banned_words" not in insp.get_table_names():
            ChatBannedWord.__table__.create(engine, checkfirst=True)
    except Exception:
        pass


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_global_settings_columns(engine)
    _migrate_bots_and_chat_bot_id(engine)
    _migrate_auto_replies_chat_id(engine)
    _migrate_chat_moderation_apply_to_admins(engine)
    _migrate_chat_content_filter_columns(engine)
    _migrate_chat_allowed_content_types(engine)
    _migrate_chat_banned_words_table(engine)
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        _ensure_global_settings(session)
        session.commit()


def _ensure_global_settings(session: Session) -> None:
    if session.get(GlobalSettings, 1) is not None:
        return
    session.add(
        GlobalSettings(
            id=1,
            primary_chat_id=0,
            bot_token=None,
            notify_on_startup=False,
            chats_config_revision=0,
            default_msg_max_length=300,
            default_msg_length_unlimited=False,
            default_echo_enabled=False,
            bot_description=None,
            bot_short_description=None,
        )
    )


def bump_chats_revision(session: Session) -> int:
    gs = session.get(GlobalSettings, 1)
    if gs is None:
        return 0
    gs.chats_config_revision = int(gs.chats_config_revision or 0) + 1
    session.flush()
    return gs.chats_config_revision
