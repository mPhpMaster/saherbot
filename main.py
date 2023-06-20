#!/usr/bin/env python
# main commands and bot creation

import telebot
from decouple import config
import re
import datetime
import glob
import os

LAST_ACTIVITY = datetime.datetime.now().timestamp()
botName = "SaherBot"
BOT_TOKEN = config('BOT_TOKEN')
MSG_LENGTH = config('MSG_LENGTH')
CHAT_ID = config('CHAT_ID')
NOTIFY_RUN = config('NOTIFY_RUN')
ALLOWED_TYPES = ['audio', 'photo', 'voice', 'video', 'text']

bot = telebot.TeleBot(BOT_TOKEN)
LIST={}
for f in glob.glob("list/*"):
    _f=open(f,"r+")
    _name=os.path.basename(f)
    LIST[ _name ] = _f.read()
    if LIST[ _name ][0] == "-":
        LIST[_name] = LIST[ os.path.basename(f) ][2:]
    _f.close()

def is_admin(user: int):
    for u in bot.get_chat_administrators(CHAT_ID):
        if u.user.id == user:
            return True

    return False


def delete_with_mention(chat_id: int, message_id: int, user_name: str, user_id: int, _message: str):
    bot.delete_message(chat_id, message_id)
    mention = "[" + user_name + "](tg://user?id=" + str(user_id) + ")"
    bot_msg = f"{mention} {_message}"
    return bot.send_message(chat_id, bot_msg, parse_mode="Markdown")


def welcome_message(id=CHAT_ID):
    global botName
    bot.send_message(id, f"{botName} is running!")

@bot.message_handler(commands=["id"])
def chat_id(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.from_user.id, f"<code>CHAT_ID={message.chat.id}</code>", parse_mode="HTML")

@bot.message_handler(commands=["ping"])
def welcome(message):
    welcome_message(message.chat.id)

@bot.message_handler(commands=["help"])
def show_codes(message):
    global LIST
    msg="\n"
    for v in LIST:
        msg += f"{v}\n"
    msg+="\n"
    bot.send_message(message.from_user.id, msg)


# Handle all other messages.
@bot.message_handler(func=lambda message: True, content_types=['audio', 'photo', 'voice', 'video', 'document',
                                                               'text', 'location', 'contact', 'sticker'])
def default_command(message):
    global LAST_ACTIVITY
    # skip private
    if message.chat.type == 'private':
        return

    # skip old messages
    if message.date and datetime.datetime.now().timestamp() > (message.date + 2):
        return

    # skip duplicate
    if LAST_ACTIVITY == datetime.datetime.now().timestamp():
        return

    LAST_ACTIVITY = datetime.datetime.now().timestamp()
    _is_admin = is_admin(message.from_user.id)
    # check message length
    if not _is_admin and len(message.text) > int(MSG_LENGTH):
        return delete_with_mention(message.chat.id, message.id, message.from_user.first_name, message.from_user.id, "الرجاء اختصار الرسالة")

    isURL = re.match(re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE), message.text) is not None

    if not _is_admin and (not (message.content_type in ALLOWED_TYPES and not isURL)):
        return delete_with_mention(message.chat.id, message.id, message.from_user.first_name, message.from_user.id, " غير مسموح لك بارسال هذه الرسالة !")

    if message.content_type == 'text' and not isURL:
        for key, val in LIST.items():
            if key.lower() == message.text.lower():
                return bot.reply_to(message, val)

        # return bot.send_message(message.chat.id, "C: " + message.text)


@bot.message_handler(content_types=[
    "new_chat_members",
    "left_chat_member"
])
def new_left_chat_members(message):
    bot.delete_message(message.chat.id,message.id)
    if not is_admin(message.from_user.id) and message.content_type == "new_chat_members":
        for member in message.new_chat_members:
            if member.is_bot == True:
                bot.ban_chat_member(message.chat.id,member.id)

if int(NOTIFY_RUN) == 1:
    welcome_message(CHAT_ID)

bot.polling()
