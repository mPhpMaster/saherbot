"""Per-thread TeleBot instance (multi-bot supervisor runs one thread per bot)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import telebot

_tls = threading.local()


def set_bot_context(bot: telebot.TeleBot, bot_id: int) -> None:
    _tls.bot = bot
    _tls.bot_id = int(bot_id)


def clear_bot_context() -> None:
    _tls.bot = None
    _tls.bot_id = None


def get_bot() -> telebot.TeleBot:
    b = getattr(_tls, "bot", None)
    if b is None:
        raise RuntimeError("TeleBot context not set (worker thread not initialized)")
    return b


def get_bot_id() -> int:
    return int(getattr(_tls, "bot_id", 0) or 0)
