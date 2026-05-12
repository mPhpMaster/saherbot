#!/usr/bin/env python
"""Supervisor: one OS process, one thread per configured bot (see dashboard Bots)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import telebot

import config_store
from bot_context import clear_bot_context, set_bot_context
from logger import log
from saherbot_db.database import get_session_factory
from saherbot_db.models import Bot
from sqlalchemy import select


def _write_supervisor_pid() -> None:
    d = Path(__file__).resolve().parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bot.pid").write_text(str(os.getpid()), encoding="utf-8")


def _remove_supervisor_pid() -> None:
    p = Path(__file__).resolve().parent / "data" / "bot.pid"
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def _load_bot_rows() -> list[Bot]:
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        rows = list(session.scalars(select(Bot).order_by(Bot.id)).all())
    return [b for b in rows if (b.bot_token or "").strip()]


def _run_one_bot(bot_row: Bot) -> None:
    import helpers
    from init import apply_gs_descriptions, register_handlers

    token = (bot_row.bot_token or "").strip()
    if not token:
        return
    bid = int(bot_row.id)
    # Handlers must run on this thread: ``threading.local`` bot_context is set here. Default
    # TeleBot ``threaded=True`` runs handlers on worker threads → get_bot_id() was 0 and APIs failed.
    bot = telebot.TeleBot(token, threaded=False)
    set_bot_context(bot, bid)
    try:
        config_store.bootstrap_monitored_cache_from_db()
        register_handlers(bot, bid)
        apply_gs_descriptions(bot)
        if bot_row.notify_on_startup:
            nid = int(bot_row.primary_chat_id or 0)
            if nid:
                try:
                    helpers.welcome_message(nid)
                except Exception as e:
                    log(f"startup notify skipped: {e}", "error")
        log(f"Bot id={bid} polling...", "info")
        bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        log(f"Bot id={bid} KeyboardInterrupt", "info")
    except Exception as e:
        log(f"Bot id={bid} polling error: {e}", "error")
    finally:
        try:
            bot.stop_polling()
        except Exception:
            pass
        clear_bot_context()


def main() -> None:
    config_store.ensure_db()
    rows = _load_bot_rows()
    if not rows:
        log(
            "No bot with a token configured: add a bot and token in the dashboard (Bots), "
            "then link chats to it.",
            "error",
        )
        raise SystemExit(1)

    _write_supervisor_pid()
    config_store.refresh_monitored_if_needed()
    import helpers

    helpers.load_lists()
    log(f"Supervisor: starting {len(rows)} bot thread(s)", "info")

    threads: list[threading.Thread] = []
    for row in rows:
        t = threading.Thread(target=_run_one_bot, args=(row,), name=f"saherbot-bot-{row.id}", daemon=False)
        t.start()
        threads.append(t)
        time.sleep(0.35)

    try:
        for t in threads:
            t.join()
    finally:
        _remove_supervisor_pid()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        raise e
    except Exception as e:
        log(f"Fatal: {e}", "error")
        raise
