import os
from pathlib import Path
import logger
import loader
import datetime
import re

import bot_context

# روابط أو نطاقات شائعة داخل الرسالة (ليس مطابقة سطر كامل)
_URL_IN_TEXT_RE = re.compile(
    r"(?:https?://|www\.|t\.me/|telegram\.me/|tg://)"
    r"|(?<![@\w.])(?:[\w-]+\.)+(?:com|net|org|io|co|me|app|dev|gov|edu|sa|ae|info|biz|ly|tv)"
    r"(?:/[\w./?#%&+=-]*)?\b",
    re.IGNORECASE,
)
# جوال سعودي شائع + أرقام دولية بصيغة + / 00
_PHONE_RE = re.compile(
    r"(?:\+?966|00966)5[0-9]{8}\b|\b05[0-9]{8}\b|\+[1-9][0-9]{9,14}\b|\b00[1-9][0-9]{9,14}\b",
)
# @username تيليجرام (مع استبعاد عناوين البريد من النص أولاً)
_EMAIL_STRIP_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
_TELEGRAM_USERNAME_RE = re.compile(
    r"(?<![A-Za-z0-9_])@([a-zA-Z][a-zA-Z0-9_]{4,31})(?![A-Za-z0-9_])",
)
_FORBIDDEN_ENTITY_TYPES = frozenset(
    {"url", "text_link", "mention", "text_mention"},
)
_ENTITY_LINK_TYPES = frozenset({"url", "text_link"})
_ENTITY_MENTION_TYPES = frozenset({"mention", "text_mention"})

# حظر بعد تكرار حذف رسائل المستخدم (غير المشرف)
STRIKE_WINDOW_SEC = 30 * 60
STRIKES_TO_BAN = 3
_moderation_strikes = {}

# Strikes for banned-word deletes only (in-memory; lost on restart). Third hit in window → kick (ban+unban).
_banned_word_strikes: dict[tuple[int, int], list[float]] = {}
BANNED_WORD_STRIKES_TO_KICK = 3

MODERATION_KICK_WARNING_SUFFIX = " سيتم طردك في حال كررت المخالفة."

# «البقاء مجهولاً»: المرسل يظهر كـ User لهذا المعرف (ومع ذلك is_bot=True في واجهة تيليجرام).
TELEGRAM_GROUP_ANONYMOUS_BOT_ID = 1087968824


_WS_COLLAPSE_RE = re.compile(r"\s+")


def normalize_telegram_chat_id(value: int | str) -> int:
    """
    Telegram supergroups/channels use negative ids like ``-1001845637233``.
    Some tools paste the same digits without the minus (``1001845637233``); map those to the API form.
    """
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("not an integer chat id") from None
    if n < 0:
        return n
    s = str(n)
    if s.startswith("100") and len(s) >= 12:
        return -n
    return n


def normalize_text_for_banned_substring_scan(text: str) -> str:
    """Whitespace collapsed to single spaces, strip, lowercase. Match is ``needle in haystack`` (substring, Arabic-safe)."""
    if not text:
        return ""
    return _WS_COLLAPSE_RE.sub(" ", text.strip()).lower()


def user_display_name_for_notice(user) -> str:
    if user is None:
        return "المستخدم"
    fn = (getattr(user, "first_name", None) or "").strip()
    ln = (getattr(user, "last_name", None) or "").strip()
    name = (fn + " " + ln).strip()
    if name:
        return name
    un = getattr(user, "username", None)
    if un and str(un).strip():
        return "@" + str(un).strip().lstrip("@")
    return "المستخدم"


def plaintext_matches_any_banned_word(chat_id: int, plain: str) -> bool:
    try:
        import config_store

        words = config_store.get_banned_words_lower_for_chat(int(chat_id))
    except Exception as e:
        logger.log("banned words load failed: " + str(e), "error")
        return False
    if not words:
        return False
    hay = normalize_text_for_banned_substring_scan(plain)
    if not hay:
        return False
    for w in words:
        if w and w in hay:
            return True
    return False


def should_apply_banned_word_scan(message) -> bool:
    if getattr(message.chat, "type", None) not in ("group", "supergroup"):
        return False
    u = getattr(message, "from_user", None)
    if u is None:
        return False
    if bool(getattr(u, "is_bot", False)) and int(getattr(u, "id", 0) or 0) != TELEGRAM_GROUP_ANONYMOUS_BOT_ID:
        return False
    blob = get_message_plaintext(message)
    return bool(blob and blob.strip())


def record_banned_word_strike_and_maybe_kick(chat_id: int, user_id: int, user_name: str) -> None:
    """Count one strike per deleted message; third violation within STRIKE_WINDOW_SEC → kick (ban then unban)."""
    if int(user_id) == TELEGRAM_GROUP_ANONYMOUS_BOT_ID:
        return
    if is_admin(user_id, chat_id) and not chat_moderation_includes_admins(chat_id):
        return
    key = (int(chat_id), int(user_id))
    t = now()
    cutoff = t - STRIKE_WINDOW_SEC
    prev = _banned_word_strikes.get(key, [])
    prev = [x for x in prev if x >= cutoff]
    prev.append(t)
    if len(prev) >= BANNED_WORD_STRIKES_TO_KICK:
        if is_admin(user_id, chat_id) and not chat_moderation_includes_admins(chat_id):
            _banned_word_strikes.pop(key, None)
            return
        try:
            b = bot_context.get_bot()
            b.ban_chat_member(chat_id, user_id)
            try:
                b.unban_chat_member(chat_id, user_id, only_if_banned=True)
            except Exception as ue:
                logger.log("unban_chat_member after kick failed: " + str(ue), "error")
            logger.log(
                "Kicked user after repeated banned-word violations: "
                + str(user_id)
                + " "
                + (user_name or "")
            )
            try:
                import config_store

                config_store.log_event(
                    "kick_banned_word_strikes",
                    chat_id,
                    {"user_id": user_id, "user_name": user_name or ""},
                )
            except Exception:
                pass
            mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
            bot_context.get_bot().send_message(
                chat_id,
                mention + " تم الطرد بسبب تكرار مخالفة الكلمات الممنوعة.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.log("kick (ban/unban) after banned-word strikes failed: " + str(e), "error")
            _banned_word_strikes[key] = prev
            return
        _banned_word_strikes.pop(key, None)
    else:
        _banned_word_strikes[key] = prev


def handle_banned_word_violation(message) -> bool:
    """Delete message when possible, always try a group notice, strike when delete OK or admin-under-moderation."""
    import html

    chat_id = int(message.chat.id)
    mid = int(message.id)
    u = message.from_user
    uid = int(u.id) if u else 0
    display = user_display_name_for_notice(u)
    b = bot_context.get_bot()
    delete_ok = False
    try:
        b.delete_message(chat_id, mid)
        delete_ok = True
    except Exception as e:
        logger.log("delete_message (banned word) failed: " + str(e), "error")

    mention = f'<a href="tg://user?id={uid}">{html.escape(display)}</a>' if uid else html.escape(display)
    if delete_ok:
        tail = "«في حال تكرارها سيتم حظرك.»"
    else:
        tail = (
            "«لم يُحذف النص — تأكد أن للبوت صلاحية «حذف الرسائل» في المجموعة "
            "(أحياناً لا يُسمح بحذف رسائل المشرفين إلا بصلاحيات كافية).» "
            "«في حال تكرار المخالفة قد يُتخذ إجراء.»"
        )
    body = "«يُمنع كتابة هذه الكلمة.» " + mention + " " + tail
    try:
        b.send_message(chat_id, body, parse_mode="HTML")
    except Exception as e:
        logger.log("send_message (banned word notice) failed: " + str(e), "error")

    apply_ad = chat_moderation_includes_admins(chat_id)
    admin_here = bool(uid) and is_admin(uid, chat_id)
    if delete_ok or (apply_ad and admin_here):
        record_banned_word_strike_and_maybe_kick(chat_id, uid, display)
    try:
        import config_store

        config_store.log_event(
            "delete_banned_word",
            chat_id,
            {"user_id": uid, "user_name": display, "deleted": delete_ok},
        )
    except Exception:
        pass
    logger.log(
        "Banned word violation chat_id="
        + str(chat_id)
        + " user="
        + user_display(u)
        + " deleted="
        + str(delete_ok)
    )
    return True


def user_display(user):
    if user is None:
        return "unknown"
    if getattr(user, "username", None):
        return user.username
    if getattr(user, "first_name", None):
        return user.first_name
    return str(getattr(user, "id", ""))


def load_lists():
    """Build ``loader.LIST`` keys from ``list/*`` file names (for ``/help`` only). Bot replies use DB ``auto_replies`` only."""
    loader.LIST.clear()
    root = Path(__file__).resolve().parent / "list"
    if not root.is_dir():
        logger.log("list/: folder missing (dashboard auto-replies only)", "info")
        return 0
    n = 0
    for p in sorted(root.glob("*")):
        if p.is_file():
            loader.LIST[p.name] = True
            n += 1
    logger.log(f"list/: {n} catalog entr(y/ies) for /help; replies from database", "info")
    return n

def is_monitored_group(chat_id):
    """True if this chat is handled by the current bot thread (explicit ``bot_id`` in DB, or one bot + unlinked chat)."""
    try:
        import config_store

        return config_store.is_chat_assigned_to_current_bot(int(chat_id))
    except (TypeError, ValueError):
        return False


def chat_for_admin_lookup(message):
    """Use the current group for admin checks; in private, use primary chat from the dashboard DB."""
    t = getattr(message.chat, "type", None)
    if t in ("group", "supergroup"):
        return message.chat.id
    import config_store

    pid = config_store.get_primary_chat_id_for_bot(bot_context.get_bot_id())
    return pid


def is_admin(user_id: int, chat_id=None):
    if chat_id is None:
        import config_store

        cid = config_store.get_primary_chat_id_for_bot(bot_context.get_bot_id())
    else:
        cid = chat_id
    if cid is None:
        return False
    try:
        cid_int = int(cid)
    except (TypeError, ValueError):
        return False
    try:
        for u in bot_context.get_bot().get_chat_administrators(cid_int):
            if u.user.id == user_id:
                return True
    except Exception as e:
        logger.log("get_chat_administrators failed: " + str(e), "error")
    return False


def chat_moderation_includes_admins(chat_id: int) -> bool:
    """When True, group admins are moderated like regular members for this chat."""
    try:
        import config_store

        s = config_store.get_effective_chat_settings(int(chat_id))
        return _coerce_db_bool(s.get("moderation_apply_to_admins"))
    except Exception:
        return False


def _coerce_db_bool(v) -> bool:
    """SQLite / drivers may return 0/1 or strings; avoid ``bool(\"false\")`` pitfalls."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return bool(v)


def moderation_applies_to_sender(message) -> bool:
    """Whether moderation rules (length, type, sharing, banned words) apply to the sender."""
    if getattr(message.chat, "type", None) not in ("group", "supergroup"):
        return False
    u = getattr(message, "from_user", None)
    if u is None:
        return False
    if bool(getattr(u, "is_bot", False)) and int(getattr(u, "id", 0) or 0) != TELEGRAM_GROUP_ANONYMOUS_BOT_ID:
        return False
    cid = int(message.chat.id)
    uid = int(u.id)
    if uid == TELEGRAM_GROUP_ANONYMOUS_BOT_ID:
        return chat_moderation_includes_admins(cid)
    if not is_admin(uid, cid):
        return True
    return chat_moderation_includes_admins(cid)


def echo_command(message):
    echo_enabled = False
    try:
        import config_store

        echo_enabled = bool(config_store.get_effective_chat_settings(message.chat.id)["echo_enabled"])
    except Exception as e:
        logger.log("DB echo settings fallback: " + str(e), "error")
    if echo_enabled:
        bot_context.get_bot().send_message(message.chat.id, "C: " + (message.text or ""))

def is_private(message):
    return message.chat.type == 'private'

def now():
    return datetime.datetime.now().timestamp()


# Telegram `message.date` is Unix seconds. A threshold of only 2 seconds wrongly treated
# almost every delivered update as "old" (long polling + handler latency). Skip only
# genuinely stale backlog; `infinity_polling(..., skip_pending=True)` already drops
# pending updates on startup.
OLD_MESSAGE_MAX_AGE_SEC = 600.0


def is_old_message(message):
    try:
        if not message.date:
            return False
        return now() > (float(message.date) + OLD_MESSAGE_MAX_AGE_SEC)
    except Exception:
        return False

def record_strike_after_moderation_delete(chat_id: int, user_id: int, user_name: str):
    """بعد حذف رسالة مخالفة: العدّ نحو الحظر عند STRIKES_TO_BAN ضمن STRIKE_WINDOW_SEC."""
    if is_admin(user_id, chat_id) and not chat_moderation_includes_admins(chat_id):
        return
    key = (chat_id, user_id)
    t = now()
    cutoff = t - STRIKE_WINDOW_SEC
    prev = _moderation_strikes.get(key, [])
    prev = [x for x in prev if x >= cutoff]
    prev.append(t)
    if len(prev) >= STRIKES_TO_BAN:
        if is_admin(user_id, chat_id) and not chat_moderation_includes_admins(chat_id):
            _moderation_strikes.pop(key, None)
            return
        try:
            bot_context.get_bot().ban_chat_member(chat_id, user_id)
            logger.log(
                "Ban after repeated moderation deletes: "
                + str(user_id)
                + " "
                + (user_name or "")
            )
            try:
                import config_store

                config_store.log_event(
                    "ban_strikes",
                    chat_id,
                    {"user_id": user_id, "user_name": user_name or ""},
                )
            except Exception:
                pass
            mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
            bot_context.get_bot().send_message(
                chat_id,
                mention + " تم الحظر بسبب تكرار المخالفات 3 مرات.",
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.log("ban_chat_member failed: " + str(e), "error")
            _moderation_strikes[key] = prev
            return
        _moderation_strikes.pop(key, None)
    else:
        _moderation_strikes[key] = prev


def delete_with_mention(
    chat_id: int,
    message_id: int,
    user_name: str,
    user_id: int,
    _message: str,
    record_strike: bool = True,
    event_type: str = "delete_moderation",
):
    try:
        bot_context.get_bot().delete_message(chat_id, message_id)
    except Exception as e:
        logger.log("delete_message failed: " + str(e), "error")
        return None
    mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
    bot_msg = f"{mention} {_message}"
    try:
        sent = bot_context.get_bot().send_message(chat_id, bot_msg, parse_mode="Markdown")
    except Exception as e:
        logger.log("send_message failed: " + str(e), "error")
        sent = None
    if record_strike:
        record_strike_after_moderation_delete(chat_id, user_id, user_name)
    try:
        import config_store

        config_store.log_event(
            event_type,
            chat_id,
            {"user_id": user_id, "user_name": user_name},
        )
    except Exception:
        pass
    return sent


def welcome_message(id=""):
    if id:
        try:
            cid = int(id)
        except (TypeError, ValueError):
            cid = id
        bot_context.get_bot().send_message(cid, f"{loader.botName} is running!")

    return

def is_type_allowed(message):
    """نوع الرسالة ضمن قائمة المحادثة في القاعدة (أو الافتراضي). الروابط تُعالج لاحقاً بمنع الروابط."""
    import config_store

    try:
        allowed = config_store.get_effective_chat_settings(int(message.chat.id)).get("allowed_content_types")
    except Exception:
        allowed = None
    if not allowed:
        allowed = list(config_store.DEFAULT_ALLOWED_CONTENT_TYPES)
    return message.content_type in allowed


def is_type_denied(message):
    return not is_type_allowed(message)


def is_text(message):
    t = message.text or ""
    return message.content_type == "text" and is_not_url(t) and not text_has_link_substring(t)

def is_url(text):
    if text is None or text == "":
        return False
    return re.match(re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE), text) is not None

def is_not_url(text):
    return is_url(text) == False


def get_message_plaintext(message):
    parts = []
    if getattr(message, "text", None):
        parts.append(message.text)
    if getattr(message, "caption", None):
        parts.append(message.caption)
    return "\n".join(parts)


def text_has_link_substring(text):
    if not text:
        return False
    return _URL_IN_TEXT_RE.search(text) is not None


def text_has_phone(text):
    if not text:
        return False
    return _PHONE_RE.search(text) is not None


def text_has_telegram_username(text):
    if not text:
        return False
    stripped = _EMAIL_STRIP_RE.sub("", text)
    return _TELEGRAM_USERNAME_RE.search(stripped) is not None


def message_entities_restricted(message):
    """Legacy: أي كيان من الروابط أو المنشن (للتوافق)."""
    return _message_has_entity_types(message, _FORBIDDEN_ENTITY_TYPES)


def _message_has_entity_types(message, types: frozenset) -> bool:
    for attr in ("entities", "caption_entities"):
        coll = getattr(message, attr, None) or []
        for ent in coll:
            if getattr(ent, "type", None) in types:
                return True
    return False


def message_violates_chat_content_filters(message) -> bool:
    """
    Per-chat (DB): block phone numbers, @username tags, and/or links in plaintext or Telegram entities.
    """
    try:
        import config_store

        cid = int(message.chat.id)
        s = config_store.get_effective_chat_settings(cid)
    except Exception:
        return False
    block_phone = bool(s.get("moderation_block_phones"))
    block_mentions = bool(s.get("moderation_block_mentions"))
    block_links = bool(s.get("moderation_block_links"))
    if not block_phone and not block_mentions and not block_links:
        return False
    blob = get_message_plaintext(message)
    if block_links:
        if text_has_link_substring(blob) or _message_has_entity_types(message, _ENTITY_LINK_TYPES):
            return True
    if block_mentions:
        if (blob and text_has_telegram_username(blob)) or _message_has_entity_types(message, _ENTITY_MENTION_TYPES):
            return True
    if block_phone and text_has_phone(blob):
        return True
    return False


def message_has_forbidden_sharing(message):
    """رقم جوال أو رابط أو @username عند تفعيل الفلترة لهذه المحادثة في لوحة التحكم."""
    return message_violates_chat_content_filters(message)


def get_list(message):
    text = message.text or ""
    try:
        import config_store

        found = config_store.find_auto_reply(message.chat.id, text)
        if found is not None:
            content, trigger = found
            logger.log(f"DB auto reply {trigger} by: " + user_display(message.from_user))
            return [content, trigger]
    except Exception as e:
        logger.log("DB auto reply error: " + str(e), "error")
    return []


def get_list_reply(message):
    return get_list(message)


def check_message_len(message):
    if message.content_type != "text":
        return False
    text = message.text
    if text is None:
        return False
    limit = None
    unlimited = False
    try:
        import config_store

        settings = config_store.get_effective_chat_settings(message.chat.id)
        unlimited = bool(settings["msg_length_unlimited"])
        limit = settings["msg_max_length"]
    except Exception as e:
        logger.log("DB length settings fallback: " + str(e), "error")
    if unlimited or limit in (None, ""):
        return False
    return len(text) > int(limit)
