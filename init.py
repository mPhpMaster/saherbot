from logger import log
import telebot
import loader
bot = telebot.TeleBot(loader.BOT_TOKEN)
import logger
import helpers


@bot.message_handler(commands=["id"])
def get_chat_id(message):
    log("Command id from " + helpers.user_display(message.from_user))
    if helpers.is_admin(message.from_user.id):
        bot.delete_message(message.chat.id, message.id)
        bot.send_message(message.from_user.id, f"<code>CHAT_ID={message.chat.id}</code>", parse_mode="HTML")
    return


@bot.message_handler(commands=["reload"])
def reload_lists(message):
    logger.log("Command reload from " + helpers.user_display(message.from_user))
    if helpers.is_admin(message.from_user.id):
        bot.delete_message(message.chat.id, message.id)
        bot.send_message(message.from_user.id, f"{helpers.load_lists()} List loaded.")
    return


@bot.message_handler(commands=["ping"])
def ping(message):
    logger.log("Command ping from " + helpers.user_display(message.from_user))
    helpers.welcome_message(message.chat.id)
    return


@bot.message_handler(commands=["help"])
def show_codes(message):
    logger.log("Command help from " + helpers.user_display(message.from_user))
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

    _is_not_admin = helpers.is_admin(message.from_user.id) == False
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
    bot.delete_message(message.chat.id, message.id)
    if not helpers.is_admin(message.from_user.id) and message.content_type == "new_chat_members":
        for member in message.new_chat_members:
            if member.is_bot == True:
                logger.log("Ban Member bot: " + helpers.user_display(member))
                bot.ban_chat_member(message.chat.id, member.id)
    return

helpers.load_lists()

if int(loader.NOTIFY_RUN) == 1:
    helpers.welcome_message(loader.CHAT_ID)

def startBot():
    logger.log(loader.botName + " Running!")
    logger.log("Ctrl+C to close it.")
    bot.polling()

    logger.log("Exit!")
    bot.stop_polling()
    return bot
