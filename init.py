# Standard library imports
import signal
import sys

# Third-party imports
import telebot

# Local imports
import loader
from logger import log
import helpers

# Initialize bot instance
bot = telebot.TeleBot(loader.BOT_TOKEN)

# Set bot instance in helpers to avoid circular imports
helpers.set_bot(bot)

# Import logger after bot initialization
import logger


@bot.message_handler(commands=["id"])
def get_chat_id(message):
    log("Command id from " + helpers.user_display(message.from_user))
    if not helpers.is_private(message) and not helpers.is_monitored_group(message.chat.id):
        return
    if helpers.is_admin(message.from_user.id, helpers.chat_for_admin_lookup(message)):
        bot.delete_message(message.chat.id, message.id)
        bot.send_message(message.from_user.id, f"<code>CHAT_ID={message.chat.id}</code>", parse_mode="HTML")
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
    if not helpers.is_private(message) and not helpers.is_monitored_group(message.chat.id):
        return
    msg = "\n"
    for v in loader.LIST:
        msg += f"{v}\n"
    msg += "\n"
    bot.delete_message(message.chat.id, message.id)
    bot.send_message(message.from_user.id, msg)
    return

@bot.message_handler(func=lambda message: True, content_types=['audio', 'photo', 'voice', 'video', 'document',
                                                               'text', 'location', 'contact', 'sticker'])
def default_command(message):
    # skip private
    if helpers.is_private(message):
        logger.log("Private message from " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
        return

    # skip old messages
    if helpers.is_old_message(message):
        logger.log("Old Message from " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
        return

    if not helpers.is_monitored_group(message.chat.id):
        return

    _is_not_admin = helpers.is_admin(message.from_user.id, message.chat.id) == False
    # check message length
    if _is_not_admin and helpers.check_message_len(message):
        logger.log("Delete Message Bad Length by " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
        return helpers.delete_with_mention(message.chat.id, message.id, message.from_user.first_name or "", message.from_user.id, "الرجاء اختصار الرسالة")

    if _is_not_admin and helpers.is_type_denied(message):
        logger.log("Delete Message Bad Type by " + helpers.user_display(message.from_user) + ": " + (message.text or ""))
        return helpers.delete_with_mention(message.chat.id, message.id, message.from_user.first_name or "", message.from_user.id, " غير مسموح لك بارسال هذه الرسالة !" + helpers.MODERATION_KICK_WARNING_SUFFIX)

    if _is_not_admin and helpers.message_has_forbidden_sharing(message):
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
            "غير مسموح بمشاركة أرقام الجوال أو الروابط أو أسماء المستخدمين."
            + helpers.MODERATION_KICK_WARNING_SUFFIX,
        )

    if helpers.is_text(message):
        val = helpers.get_list(message)
        if len(val):
            val = val[0]
            if isinstance(val, str):
                return bot.reply_to(message, val)

            if 'path' in val:
                return bot.send_photo(message.chat.id, photo=open(val['path'], 'rb'), reply_to_message_id=message.id)

        helpers.echo_command(message)

@bot.message_handler(content_types=[
    "new_chat_members",
    "left_chat_member"
])
def new_left_chat_members(message):
    logger.log("Delete Message new_chat_members/left_chat_member by " + helpers.user_display(message.from_user))
    if not helpers.is_monitored_group(message.chat.id):
        return
    bot.delete_message(message.chat.id, message.id)
    if not helpers.is_admin(message.from_user.id, message.chat.id) and message.content_type == "new_chat_members":
        for member in message.new_chat_members:
            if member.is_bot == True:
                logger.log("Ban Member bot: " + helpers.user_display(member))
                bot.ban_chat_member(message.chat.id, member.id)
    return

helpers.load_lists()

if int(loader.NOTIFY_RUN) == 1:
    helpers.welcome_message(loader.CHAT_ID)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.log(f"Received signal {signum}, shutting down gracefully...")
    try:
        bot.stop_polling()
    except Exception:
        pass
    sys.exit(0)


def startBot():
    """Start the bot with graceful shutdown handling."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.log(loader.botName + " Running!")
    logger.log("Press Ctrl+C to stop.")
    
    # infinity_polling: survives Telegram 5xx (e.g. 502 Bad Gateway) and network blips
    try:
        bot.infinity_polling(
            skip_pending=True,
            timeout=60,
            long_polling_timeout=60,
        )
    except KeyboardInterrupt:
        logger.log("Exit (KeyboardInterrupt)!")
    except Exception as e:
        logger.log(f"Polling error: {e}", "error")
    finally:
        try:
            bot.stop_polling()
        except Exception:
            pass
    return bot
