"""ORM models: global settings, chats, events, auto-replies."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Bot(Base):
    """One Telegram bot identity (token); chats link here for moderation."""

    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    bot_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notify_on_startup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    primary_chat_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


class GlobalSettings(Base):
    """Single configuration row (id=1)."""

    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    primary_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bot_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notify_on_startup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chats_config_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    default_msg_max_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_msg_length_unlimited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_echo_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_short_description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Chat(Base):
    __tablename__ = "chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    moderation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    msg_max_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    msg_length_unlimited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    echo_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    moderation_apply_to_admins: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    moderation_block_phones: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    moderation_block_mentions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    moderation_block_links: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allowed_content_types: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    moderation_rules: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    meta_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class ChatBannedWord(Base):
    """Per-group forbidden substrings (stored lowercased for case-insensitive uniqueness on SQLite)."""

    __tablename__ = "chat_banned_words"
    __table_args__ = (UniqueConstraint("chat_id", "word", name="uq_chat_banned_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False, index=True)
    word: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class AutoReply(Base):
    __tablename__ = "auto_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(512), nullable=False)
    response_type: Mapped[str] = mapped_column(String(16), nullable=False)
    response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
