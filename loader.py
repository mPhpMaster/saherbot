from decouple import config
from logger import log

botName = "SaherBot"
BOT_TOKEN = config('BOT_TOKEN')
MSG_LENGTH = config('MSG_LENGTH')
NOTIFY_RUN = config('NOTIFY_RUN')
ECHO_COMMAND = config('ECHO_COMMAND')
CHAT_ID = config('CHAT_ID')
ALLOWED_TYPES = ['audio', 'photo', 'voice', 'video', 'text']
LIST = {}

if len(BOT_TOKEN) == 0:
    log("MISSING: BOT_TOKEN", "error")
    exit()

if len(CHAT_ID) == 0:
    log("MISSING: CHAT_ID", "error")
    exit()
