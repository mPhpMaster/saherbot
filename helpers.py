import glob
import os
import logger
import loader
import datetime
import re
from init import bot

# روابط أو نطاقات شائعة داخل الرسالة (ليس مطابقة سطر كامل)
_URL_IN_TEXT_RE = re.compile(
    r"(?:https?://|www\.|t\.me/|telegram\.me/|tg://)",
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

# حظر بعد تكرار حذف رسائل المستخدم (غير المشرف)
STRIKE_WINDOW_SEC = 30 * 60
STRIKES_TO_BAN = 3
_moderation_strikes = {}

MODERATION_KICK_WARNING_SUFFIX = " سيتم طردك في حال كررت المخالفة."


def user_display(user):
    if user is None:
        return "unknown"
    if getattr(user, "username", None):
        return user.username
    if getattr(user, "first_name", None):
        return user.first_name
    return str(getattr(user, "id", ""))


def load_lists():
    for f in glob.glob("list/*"):
        _f = open(f, "r")
        _name = os.path.basename(f)
        try:
            loader.LIST[_name] = _f.read()
        except:
            loader.LIST[_name] = {
                "path": f,
            }

        _f.close()
        if "path" in loader.LIST[_name]:
            loader.LIST[_name] = loader.LIST[_name]
        elif loader.LIST[_name][0] == "-":
            loader.LIST[_name] = loader.LIST[os.path.basename(f)][2:]
        else:
            loader.LIST[_name] = [f]

    list_len = len(loader.LIST.items())
    logger.log(str(list_len) + " List/Lists Read Done")
    return list_len

def is_admin(user: int):
    for u in bot.get_chat_administrators(loader.CHAT_ID):
        if u.user.id == user:
            return True

    return False

def echo_command(message):
    if str(loader.ECHO_COMMAND) == "1":
        bot.send_message(message.chat.id, "C: " + (message.text or ""))

def is_private(message):
    return message.chat.type == 'private'

def now():
    return datetime.datetime.now().timestamp()

def is_old_message(message):
    try:
        return message.date and now() > (message.date + 2)
    except:
        return False

def record_strike_after_moderation_delete(chat_id: int, user_id: int, user_name: str):
    """بعد حذف رسالة مخالفة: العدّ نحو الحظر عند STRIKES_TO_BAN ضمن STRIKE_WINDOW_SEC."""
    if is_admin(user_id):
        return
    key = (chat_id, user_id)
    t = now()
    cutoff = t - STRIKE_WINDOW_SEC
    prev = _moderation_strikes.get(key, [])
    prev = [x for x in prev if x >= cutoff]
    prev.append(t)
    if len(prev) >= STRIKES_TO_BAN:
        if is_admin(user_id):
            _moderation_strikes.pop(key, None)
            return
        try:
            bot.ban_chat_member(chat_id, user_id)
            logger.log(
                "Ban after repeated moderation deletes: "
                + str(user_id)
                + " "
                + (user_name or "")
            )
            mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
            bot.send_message(
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
):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.log("delete_message failed: " + str(e), "error")
        return None
    mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
    bot_msg = f"{mention} {_message}"
    try:
        sent = bot.send_message(chat_id, bot_msg, parse_mode="Markdown")
    except Exception as e:
        logger.log("send_message failed: " + str(e), "error")
        sent = None
    if record_strike:
        record_strike_after_moderation_delete(chat_id, user_id, user_name)
    return sent


def welcome_message(id=""):
    if id:
        bot.send_message(id, f"{loader.botName} is running!")

    return

def is_type_allowed(message):
    if message.content_type not in loader.ALLOWED_TYPES:
        return False
    if message.content_type == "text":
        t = message.text or ""
        return is_not_url(t) and not text_has_link_substring(t)
    if getattr(message, "caption", None):
        c = message.caption or ""
        if not is_not_url(c) or text_has_link_substring(c):
            return False
    return True


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
    """كيانات تيليجرام: روابط، منشن، إلخ."""
    for attr in ("entities", "caption_entities"):
        coll = getattr(message, attr, None) or []
        for ent in coll:
            t = getattr(ent, "type", None)
            if t in _FORBIDDEN_ENTITY_TYPES:
                return True
    return False


def message_has_forbidden_sharing(message):
    """رقم جوال أو رابط أو @username في النص أو التعليق أو الكيانات."""
    if message_entities_restricted(message):
        return True
    blob = get_message_plaintext(message)
    if not blob.strip():
        return False
    return (
        text_has_link_substring(blob)
        or text_has_phone(blob)
        or text_has_telegram_username(blob)
    )


def get_list(message):
    text = message.text or ""
    for key, val in loader.LIST.items():
        if key.lower() == text.lower():
            logger.log(f"List {key} by: " + user_display(message.from_user))
            return [val, key]

    return []


def check_message_len(message):
    if message.content_type != "text":
        return False
    text = message.text
    if text is None:
        return False
    return len(text) > int(loader.MSG_LENGTH)
