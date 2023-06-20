import glob
import os
import logger
import loader
import datetime
import re
from init import bot


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
        bot.send_message(message.chat.id, "C: " + message.text)

def is_private(message):
    return message.chat.type == 'private'

def now():
    return datetime.datetime.now().timestamp()

def is_old_message(message):
    try:
        return message.date and now() > (message.date + 2)
    except:
        return False

def delete_with_mention(chat_id: int, message_id: int, user_name: str, user_id: int, _message: str):
    bot.delete_message(chat_id, message_id)
    mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
    bot_msg = f"{mention} {_message}"
    return bot.send_message(chat_id, bot_msg, parse_mode="Markdown")


def welcome_message(id=""):
    if id:
        bot.send_message(id, f"{loader.botName} is running!")

    return

def is_type_allowed(message):
    return (not message.content_type in loader.ALLOWED_TYPES) and is_not_url(message.text)


def is_type_denied(message):
    return not is_type_allowed(message)


def is_text(message):
    return message.content_type == 'text' and is_not_url(message.text)

def is_url(text):
    return re.match(re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE), text) is not None

def is_not_url(text):
    return is_url(text) == False

def get_list(message):
    for key, val in loader.LIST.items():
        if key.lower() == message.text.lower():
            logger.log(f"List {key} by: " + message.from_user.username)
            return [val, key]

    return []


def check_message_len(message):
    return len(message.text) > int(loader.MSG_LENGTH)
