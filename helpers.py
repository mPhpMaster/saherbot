import glob
import os
import datetime
import re
import threading
from typing import Optional, Dict, List, Any, FrozenSet

# Import loader first (no circular dependency)
import loader
import logger

# Bot will be passed as parameter to avoid circular import
# from init import bot  # REMOVED - causes circular import

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
_moderation_strikes: Dict[tuple, List[float]] = {}
_moderation_strikes_lock = threading.Lock()

MODERATION_KICK_WARNING_SUFFIX = " سيتم طردك في حال كررت المخالفة."

# Bot instance - set via set_bot() to avoid circular import
_bot_instance = None


def set_bot(bot):
    """Set the bot instance to avoid circular imports."""
    global _bot_instance
    _bot_instance = bot


def get_bot():
    """Get the bot instance."""
    if _bot_instance is None:
        raise RuntimeError("Bot instance not initialized. Call set_bot() first.")
    return _bot_instance


def user_display(user):
    if user is None:
        return "unknown"
    if getattr(user, "username", None):
        return user.username
    if getattr(user, "first_name", None):
        return user.first_name
    return str(getattr(user, "id", ""))


def load_lists() -> int:
    """Load list files from the 'list/' directory into loader.LIST.
    
    Returns:
        int: Number of lists loaded.
    """
    list_files = glob.glob("list/*")
    for filepath in list_files:
        _name = os.path.basename(filepath)
        try:
            with open(filepath, "r", encoding="utf-8") as _f:
                content = _f.read()
                loader.LIST[_name] = content
        except UnicodeDecodeError:
            # Fallback for non-UTF-8 files
            try:
                with open(filepath, "r", encoding="latin-1") as _f:
                    content = _f.read()
                    loader.LIST[_name] = content
            except Exception as e:
                logger.log(f"Failed to read {_name}: {e}", "error")
                loader.LIST[_name] = {"path": filepath}
        except Exception as e:
            logger.log(f"Failed to read {_name}: {e}", "error")
            loader.LIST[_name] = {"path": filepath}

        # Process list entries
        if "path" in loader.LIST[_name]:
            # Keep as path dict
            pass
        elif isinstance(loader.LIST[_name], str) and loader.LIST[_name].startswith("-"):
            # Remove first two characters if starts with "-"
            loader.LIST[_name] = loader.LIST[_name][2:]
        else:
            # Convert to list with filepath
            loader.LIST[_name] = [filepath]

    list_len = len(loader.LIST)
    logger.log(f"{list_len} List/Lists Read Done")
    return list_len

def is_monitored_group(chat_id):
    """If MONITORED_CHAT_IDS is set in .env, only those groups are moderated; otherwise all groups."""
    if not loader.MONITORED_CHAT_IDS:
        return True
    try:
        return int(chat_id) in loader.MONITORED_CHAT_IDS
    except (TypeError, ValueError):
        return False


def chat_for_admin_lookup(message):
    """Use the current group for admin checks; in private, use CHAT_ID from .env."""
    t = getattr(message.chat, "type", None)
    if t in ("group", "supergroup"):
        return message.chat.id
    return loader.CHAT_ID


# Admin list cache with TTL to reduce API calls
_admin_cache: Dict[int, tuple] = {}  # chat_id -> (timestamp, set of admin user_ids)
_ADMIN_CACHE_TTL = 60  # seconds
_admin_cache_lock = threading.Lock()


def _get_admins_from_cache(chat_id: int) -> Optional[FrozenSet[int]]:
    """Get admins from cache if not expired."""
    with _admin_cache_lock:
        if chat_id in _admin_cache:
            timestamp, admin_ids = _admin_cache[chat_id]
            if datetime.datetime.now().timestamp() - timestamp < _ADMIN_CACHE_TTL:
                return admin_ids
            # Expired, remove it
            del _admin_cache[chat_id]
    return None


def _cache_admins(chat_id: int, admin_ids: FrozenSet[int]):
    """Cache admin IDs with current timestamp."""
    with _admin_cache_lock:
        _admin_cache[chat_id] = (datetime.datetime.now().timestamp(), admin_ids)


def is_admin(user_id: int, chat_id=None) -> bool:
    """Check if user is admin in the specified chat.
    
    Uses caching to reduce Telegram API calls.
    
    Args:
        user_id: The user ID to check
        chat_id: The chat ID (defaults to loader.CHAT_ID)
    
    Returns:
        bool: True if user is admin, False otherwise
    """
    cid = loader.CHAT_ID if chat_id is None else chat_id
    
    # Check cache first
    cached_admins = _get_admins_from_cache(cid)
    if cached_admins is not None:
        return user_id in cached_admins
    
    # Fetch from Telegram API
    try:
        bot_instance = get_bot()
        admins = bot_instance.get_chat_administrators(cid)
        admin_ids = frozenset(admin.user.id for admin in admins)
        
        # Cache the result
        _cache_admins(cid, admin_ids)
        
        return user_id in admin_ids
    except Exception as e:
        logger.log(f"get_chat_administrators failed: {e}", "error")
        return False

def echo_command(message):
    """Echo command for debugging purposes."""
    if str(loader.ECHO_COMMAND) == "1":
        try:
            bot_instance = get_bot()
            bot_instance.send_message(message.chat.id, f"C: {message.text or ''}")
        except Exception as e:
            logger.log(f"echo_command failed: {e}", "error")

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
    """Record a strike after moderation delete. Ban user after STRIKES_TO_BAN within STRIKE_WINDOW_SEC."""
    # Skip admins
    if is_admin(user_id, chat_id):
        return
    
    key = (chat_id, user_id)
    t = now()
    cutoff = t - STRIKE_WINDOW_SEC
    
    with _moderation_strikes_lock:
        prev = _moderation_strikes.get(key, [])
        prev = [x for x in prev if x >= cutoff]
        prev.append(t)
        
        if len(prev) >= STRIKES_TO_BAN:
            # Double-check admin status inside lock
            if is_admin(user_id, chat_id):
                _moderation_strikes.pop(key, None)
                return
            
            try:
                bot_instance = get_bot()
                bot_instance.ban_chat_member(chat_id, user_id)
                logger.log(
                    f"Ban after repeated moderation deletes: {user_id} {user_name or ''}"
                )
                mention = f"[{user_name}](tg://user?id={user_id})"
                bot_instance.send_message(
                    chat_id,
                    f"{mention} تم الحظر بسبب تكرار المخالفات 3 مرات.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                logger.log(f"ban_chat_member failed: {e}", "error")
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
    """Delete a message and send a mention with warning.
    
    Args:
        chat_id: The chat ID
        message_id: The message ID to delete
        user_name: User's display name
        user_id: User's ID for mention
        _message: Warning message to send
        record_strike: Whether to record a moderation strike
    
    Returns:
        The sent message object or None
    """
    try:
        bot_instance = get_bot()
        bot_instance.delete_message(chat_id, message_id)
    except Exception as e:
        logger.log(f"delete_message failed: {e}", "error")
        return None
    
    mention = f"[{user_name}](tg://user?id={user_id})"
    bot_msg = f"{mention} {_message}"
    
    try:
        bot_instance = get_bot()
        sent = bot_instance.send_message(chat_id, bot_msg, parse_mode="Markdown")
    except Exception as e:
        logger.log(f"send_message failed: {e}", "error")
        sent = None
    
    if record_strike:
        record_strike_after_moderation_delete(chat_id, user_id, user_name)
    
    return sent


def welcome_message(id=""):
    """Send a welcome/running message to the specified chat."""
    if id:
        try:
            bot_instance = get_bot()
            bot_instance.send_message(id, f"{loader.botName} is running!")
        except Exception as e:
            logger.log(f"welcome_message failed: {e}", "error")
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
    """Look up a message text against loaded lists.
    
    Args:
        message: Telegram message object
    
    Returns:
        list: [value, key] if found, empty list otherwise
    """
    text = message.text or ""
    for key, val in loader.LIST.items():
        if key.lower() == text.lower():
            logger.log(f"List {key} by: {user_display(message.from_user)}")
            return [val, key]

    return []


def check_message_len(message) -> bool:
    """Check if message text exceeds the configured length limit.
    
    Args:
        message: Telegram message object
    
    Returns:
        bool: True if message exceeds length limit, False otherwise
    """
    if message.content_type != "text":
        return False
    text = message.text
    if text is None:
        return False
    try:
        return len(text) > int(loader.MSG_LENGTH)
    except (ValueError, TypeError):
        logger.log(f"Invalid MSG_LENGTH config: {loader.MSG_LENGTH}", "error")
        return False
