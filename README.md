# SaherBot telegram python
Custom Bot telegram.

#packages you need to install

$ pip install pyTelegramBotAPI

$ pip install python-decouple
[SaherUser@Bot.md](..%2FSaherUser%40Bot.md)

## How To:
1. Copy `.env.example` to `.env`.
2. Chat with @BotFather in telegram app to create new bot.
3. Put your bot token in .env file.
    > BOT_TOKEN=#######:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
4. Invite the bot to your group (with admin permissions).
5. Type `/id`, you'll receive message with group/chat id.
6. Put group/chat id in the .env file.
7. run:
```shell
python main.py
```