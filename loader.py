from decouple import config
import re
from logger import log

botName = "SaherBot"
BOT_TOKEN = config('BOT_TOKEN')
MSG_LENGTH = config('MSG_LENGTH')
NOTIFY_RUN = config('NOTIFY_RUN')
ECHO_COMMAND = config('ECHO_COMMAND')
CHAT_ID = config('CHAT_ID')
ALLOWED_TYPES = ['audio', 'photo', 'voice', 'video', 'text']
LIST = {}

# Validate BOT_TOKEN format (basic regex check)
if not BOT_TOKEN or not re.match(r'^[0-9]+:[A-Za-z0-9_-]{35}$', BOT_TOKEN):
    log("Invalid BOT_TOKEN format. Expected format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz", "error")
    exit(1)

_raw_monitored = config('MONITORED_CHAT_IDS', default='').strip()
MONITORED_CHAT_IDS = frozenset()
if _raw_monitored:
    _parts = []
    for _p in _raw_monitored.split(','):
        _p = _p.strip()
        if not _p:
            continue
        try:
            _parts.append(int(_p))
        except ValueError:
            log(f"Invalid MONITORED_CHAT_IDS entry (must be integers): {_p}", "error")
            exit(1)
    MONITORED_CHAT_IDS = frozenset(_parts)
    log(f"MONITORED_CHAT_IDS active: {len(MONITORED_CHAT_IDS)} chat(s)", "info")

if len(BOT_TOKEN) == 0:
    log("MISSING: BOT_TOKEN", "error")
    exit(1)

if len(CHAT_ID) == 0:
    log("MISSING: CHAT_ID", "error")
    exit(1)

if MONITORED_CHAT_IDS:
    try:
        _primary = int(str(CHAT_ID).strip())
    except ValueError:
        log("Invalid CHAT_ID (must be integer)", "error")
        exit(1)
    if _primary not in MONITORED_CHAT_IDS:
        log("CHAT_ID must be one of the ids in MONITORED_CHAT_IDS when that list is set.", "error")
        exit(1)
