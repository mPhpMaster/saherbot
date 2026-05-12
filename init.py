"""Register Telegram handlers on a TeleBot instance (multi-bot: one thread per bot)."""

from __future__ import annotations

import telebot
import logger
import config_store
import helpers
import bot_context

# Throttle: log once per chat_id when messages are ignored (wrong dashboard link / wrong id).
_skip_unmonitored_log_at: dict[int, float] = {}


def apply_gs_descriptions(bot: telebot.TeleBot) -> None:
    try:
        from saherbot_db.database import get_session_factory
        from saherbot_db.models import GlobalSettings

        SessionLocal = get_session_factory()
        with SessionLocal() as session:
            gs = session.get(GlobalSettings, 1)
            if gs:
                if gs.bot_description and str(gs.bot_description).strip():
                    bot.set_my_description(str(gs.bot_description).strip()[:512])
                if gs.bot_short_description and str(gs.bot_short_description).strip():
                    bot.set_my_short_description(str(gs.bot_short_description).strip()[:120])
    except Exception as e:
        logger.log("set_my_description skipped: " + str(e), "error")


def register_handlers(bot: telebot.TeleBot, bot_id: int) -> None:
    @bot.message_handler(commands=["id"])
    def get_chat_id(message):
        logger.log("Command id from " + helpers.user_display(message.from_user))
        if helpers.is_private(message):
            return
        if not helpers.is_admin(message.from_user.id, message.chat.id):
            return
        try:
            bot.delete_message(message.chat.id, message.id)
        except Exception as e:
            logger.log("Command /id delete_message: " + str(e), "error")
        try:
            bot.send_message(
                message.from_user.id,
                f"<code>CHAT_ID={message.chat.id}</code>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.log("Command /id send_message: " + str(e), "error")
        return

    @bot.message_handler(commands=["reload"])
    def reload_lists(message):
        logger.log("Command reload from " + helpers.user_display(message.from_user))
        if not helpers.is_private(message) and not helpers.is_monitored_group(message.chat.id):
            return
        if helpers.is_admin(message.from_user.id, helpers.chat_for_admin_lookup(message)):
            bot.delete_message(message.chat.id, message.id)
            bot.send_message(message.from_user.id, f"{helpers.load_lists()} List loaded.")
        return

    @bot.message_handler(commands=["ping"])
    def ping(message):
        logger.log("Command ping from " + helpers.user_display(message.from_user))
        if not helpers.is_private(message) and not helpers.is_monitored_group(message.chat.id):
            return
        helpers.welcome_message(message.chat.id)
        return

    @bot.message_handler(commands=["help"])
    def show_codes(message):
        logger.log("Command help from " + helpers.user_display(message.from_user))
        # In private chat, ``message.chat.id`` is the user id — not a group; listing triggers
        # would always be empty unless we use the bot's primary group (if set).
        if helpers.is_private(message):
            bid = int(bot_context.get_bot_id() or 0)
            primary = config_store.get_primary_chat_id_for_bot(bid) if bid > 0 else None
            if primary:
                triggers = config_store.list_auto_reply_triggers_for_chat(int(primary))
                if triggers:
                    msg = (
                        "\nقائمة المحفّزات للمجموعة الرئيسية المربوطة بالبوت "
                        f"({primary}):\n\n"
                        + "\n".join(triggers)
                        + "\n\nلعرض محفّزات مجموعة أخرى، أرسل /help من داخل تلك المجموعة.\n"
                    )
                else:
                    msg = (
                        "\nلا توجد ردود تلقائية مسجّلة للمجموعة الرئيسية في لوحة التحكم.\n\n"
                        "لعرض محفّزات مجموعة مربوطة، أرسل /help من داخل المجموعة نفسها.\n"
                    )
            else:
                msg = (
                    "\nلعرض قائمة المحفّزات، أرسل الأمر /help من داخل المجموعة المربوطة بالبوت.\n\n"
                    "يمكنك تعيين «مجموعة رئيسية» للبوت من لوحة التحكم لعرض المحفّزات هنا من المحادثة الخاصة.\n"
                )
            bot.send_message(message.chat.id, msg)
            return
        if not helpers.is_monitored_group(message.chat.id):
            return
        triggers = config_store.list_auto_reply_triggers_for_chat(int(message.chat.id))
        if triggers:
            msg = "\n" + "\n".join(triggers) + "\n\n"
        else:
            msg = "\nلا توجد ردود تلقائية مسجّلة لهذه المحادثة في لوحة التحكم.\n\n"
        bot.delete_message(message.chat.id, message.id)
        bot.send_message(message.from_user.id, msg)
        return

    @bot.message_handler(
        func=lambda message: True,
        content_types=[
            "audio",
            "photo",
            "voice",
            "video",
            "document",
            "text",
            "location",
            "contact",
            "sticker",
        ],
    )
    def default_command(message):
        try:
            if helpers.is_private(message):
                logger.log("Private message from " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
                return

            if helpers.is_old_message(message):
                logger.log("Old Message from " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
                return

            if not helpers.is_monitored_group(message.chat.id):
                ct = getattr(message.chat, "type", None)
                if ct in ("group", "supergroup"):
                    cid = int(message.chat.id)
                    t = helpers.now()
                    last = _skip_unmonitored_log_at.get(cid, 0.0)
                    if t - last >= 180.0:
                        _skip_unmonitored_log_at[cid] = t
                        try:
                            bid = int(bot_context.get_bot_id())
                            watched = config_store.monitored_chat_ids_for_bot_id(bid)
                        except Exception:
                            bid, watched = 0, []
                        logger.log(
                            "تجاهل رسائل من مجموعة غير مربوطة بهذا التوكن: "
                            f"chat_id={cid} bot_dashboard_id={bid}. "
                            f"المحادثات المربوطة بهذا البوت في الذاكرة: {watched}. "
                            "أضف هذا المعرف في لوحة التحكم مع ربطه بهذا البوت (أو استخدم /id كمشرف للتأكد من المعرف).",
                            "warning",
                        )
                return

            if config_store.is_chat_monitored_use_dashboard(message.chat.id):
                if helpers.moderation_applies_to_sender(message) and helpers.check_message_len(message):
                    logger.log("Delete Message Bad Length by " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
                    return helpers.delete_with_mention(
                        message.chat.id,
                        message.id,
                        message.from_user.first_name or "",
                        message.from_user.id,
                        "الرجاء اختصار الرسالة",
                        event_type="delete_length",
                    )

                if helpers.moderation_applies_to_sender(message) and helpers.is_type_denied(message):
                    logger.log("Delete Message Bad Type by " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
                    return helpers.delete_with_mention(
                        message.chat.id,
                        message.id,
                        message.from_user.first_name or "",
                        message.from_user.id,
                        " غير مسموح لك بارسال هذه الرسالة !" + helpers.MODERATION_KICK_WARNING_SUFFIX,
                        event_type="delete_bad_type",
                    )

                if helpers.moderation_applies_to_sender(message) and helpers.message_has_forbidden_sharing(message):
                    logger.log(
                        "Delete Message forbidden sharing by "
                        + helpers.user_display(message.from_user)
                        + ": "
                        + (helpers.get_message_plaintext(message) or "")
                    )
                    return helpers.delete_with_mention(
                        message.chat.id,
                        message.id,
                        message.from_user.first_name or "",
                        message.from_user.id,
                        "غير مسموح بمشاركة أرقام الجوال أو الروابط أو تاق المستخدمين (حسب إعدادات المجموعة في لوحة التحكم)."
                        + helpers.MODERATION_KICK_WARNING_SUFFIX,
                        event_type="delete_forbidden_share",
                    )

                if helpers.moderation_applies_to_sender(message) and helpers.should_apply_banned_word_scan(message):
                    plain = helpers.get_message_plaintext(message)
                    if helpers.plaintext_matches_any_banned_word(message.chat.id, plain):
                        helpers.handle_banned_word_violation(message)
                        return

            if helpers.is_text(message):
                raw = helpers.get_list_reply(message)
                if len(raw):
                    content = raw[0]
                    trigger_key = raw[1] if len(raw) > 1 else ""
                    if isinstance(content, str):
                        r = bot.reply_to(message, content)
                        try:
                            config_store.log_event(
                                "list_reply",
                                message.chat.id,
                                {"trigger": trigger_key, "user_id": message.from_user.id},
                            )
                        except Exception:
                            pass
                        return r

                    if isinstance(content, dict) and "path" in content:
                        r = bot.send_photo(
                            message.chat.id,
                            photo=open(content["path"], "rb"),
                            reply_to_message_id=message.id,
                        )
                        try:
                            config_store.log_event(
                                "list_reply",
                                message.chat.id,
                                {"trigger": trigger_key, "user_id": message.from_user.id, "type": "photo"},
                            )
                        except Exception:
                            pass
                        return r

                helpers.echo_command(message)
        except Exception as e:
            cid = getattr(getattr(message, "chat", None), "id", None)
            logger.log(f"default_command error chat_id={cid}: {e}", "error")

    @bot.message_handler(
        content_types=[
            "new_chat_members",
            "left_chat_member",
        ]
    )
    def new_left_chat_members(message):
        logger.log("Delete Message new_chat_members/left_chat_member by " + helpers.user_display(message.from_user))
        if not helpers.is_monitored_group(message.chat.id):
            return
        bot.delete_message(message.chat.id, message.id)
        if not helpers.is_admin(message.from_user.id, message.chat.id) and message.content_type == "new_chat_members":
            for member in message.new_chat_members:
                if member.is_bot is True:
                    logger.log("Ban Member bot: " + helpers.user_display(member))
                    bot.ban_chat_member(message.chat.id, member.id)
        return
