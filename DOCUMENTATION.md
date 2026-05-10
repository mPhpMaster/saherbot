# SaherBot documentation — what does the bot do?

A Telegram bot built with Python (`pyTelegramBotAPI`) to manage a specific group: auto-replies from files, content moderation, and bans on repeated violations. The bot is intended to run mainly in a **group** (private chats are not moderated for normal messages).

---

## Startup

- Entry point: `main.py` → calls `init.startBot()`.
- Settings are read from `.env` via `python-decouple` in `loader.py`.
- On startup the `list/` folder is loaded (`helpers.load_lists()`), then `bot.infinity_polling()` starts (retries on Telegram **502/503** and short outages; plain `polling()` would exit on the first API error).

---

## Environment variables (`.env`)


| Variable             | Meaning                                                                                                                                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BOT_TOKEN`          | Bot token from BotFather (required).                                                                                                                                                                                                                                |
| `CHAT_ID`            | Required “primary” chat ID: startup notification (`NOTIFY_RUN`) and admin checks **in private** (e.g. `/id` from DM). Moderation in each group uses **that group’s** admin list.                                                                                    |
| `MONITORED_CHAT_IDS` | Optional. Comma-separated group/supergroup IDs (e.g. `-1001..., -1002...`). When set, the bot **only** applies moderation, list replies, join cleanup, and group commands in those chats. Must include `CHAT_ID`. Leave empty to moderate every chat the bot is in. |
| `MSG_LENGTH`         | Max length for a text message from non-admins; longer messages are deleted with a warning.                                                                                                                                                                          |
| `NOTIFY_RUN`         | If `1`, the bot sends a “bot is running” message to `CHAT_ID` on startup.                                                                                                                                                                                           |
| `ECHO_COMMAND`       | If `1`, the bot echoes the message text prefixed with `C:` when it does not match any list keyword (useful for debugging).                                                                                                                                          |


Allowed content types for filtering are defined in `loader.py` as `ALLOWED_TYPES`: text, photo, voice, video, audio.

### Multiple groups (same bot)

- Add the **same** bot to another group/supergroup and give it the same admin rights (delete messages, ban, etc.).
- **Do not** run a second `python main.py` with the **same** token (Telegram allows only one active session per bot token).
- Rules, `list/` replies, strikes, and “who is admin” apply **per chat** using `message.chat.id`.
- Keep `CHAT_ID` in `.env` as your “home” group: `NOTIFY_RUN=1` only pings that ID; if someone uses commands from **private**, admin permission is checked against `CHAT_ID`.
- To watch **only** specific groups at once, set `MONITORED_CHAT_IDS` to a comma-separated list and set `CHAT_ID` to one of those IDs (see table above).

---

## Commands


| Command   | Who can use it  | Behavior                                                                                                                    |
| --------- | --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `/id`     | **Admins only** | Deletes the message in the group and sends `CHAT_ID=...` to the user in private (HTML). Handy for discovering the group ID. |
| `/reload` | **Admins only** | Reloads all `list/*` files, deletes the command in the group, and tells the admin how many lists were loaded.               |
| `/ping`   | Everyone        | Calls `welcome_message` for the group (simple running notice).                                                              |
| `/help`   | Everyone        | Deletes the message in the group and sends the list file names (keys of `loader.LIST`) to the user in private.              |


---

## Group message handling

### What is skipped

1. **Private chats**: If the chat is private, the event is only logged; no moderation runs.
2. **Old messages**: If more than two seconds have passed since `message.date`, the message is ignored (reduces reactions to backlog after restarts).

### Check order for non-admins

For users who are **not** administrators of the group (`CHAT_ID`):

1. **Text length**: If the message is text and longer than `MSG_LENGTH`, it is deleted with a request to shorten (`delete_with_mention`).
2. **Content type**: If the type is not allowed (e.g. sticker, location, contact, document…) or the text/caption contains a full URL or a URL-like substring, the message is deleted with a warning.
3. **Forbidden sharing**: Delete if found in text, caption, or **Telegram entities**:
  - Links (patterns such as `http`, `www`, `t.me`, `telegram.me`, `tg://`);
  - Phone numbers (common Saudi formats and international `+` or `00` forms);
  - Telegram `@username` (email addresses in the text are stripped first);
  - Or entity types: `url`, `text_link`, `mention`, `text_mention`.

The warning text includes a fixed line that repeated violations may lead to removal (`MODERATION_KICK_WARNING_SUFFIX`).

### Strike system and bans

- After each moderation delete (length, type, forbidden sharing), a **strike** is recorded for the user within a time window (30 minutes).
- At **3 strikes** inside that window: the member is banned from the group and a notice explains why.
- Admins do not accrue strikes and are not banned by this logic.

### Auto-replies (`list/` folder)

- Each file under `list/` becomes a **key** named like the file (e.g. `list/الدبل` → key `الدبل`).
- If a member sends text that matches the file name (case-insensitive):
  - If the value is a **string** (`str`): the bot replies with that text.
  - If the value has a `**path`**: the file is treated as an image and sent as a photo with `reply_to` the message.
- `load_lists()` behavior:
  - Try to read the file as text; on failure it is treated as binary and the path is stored for photo sending.
  - If text content starts with `-`, **everything after the first two characters** is the reply (e.g. a line `-` then a link).
  - Otherwise the code stores a list containing the file path; with the current handler this may not produce a text/photo reply and may fall through to `echo_command` if enabled.

If the text matches no list and the message is valid plain text (no full-line URL), `echo_command` runs according to `ECHO_COMMAND`.

---

## Member events

- On `new_chat_members` or `left_chat_member`: the system message is always deleted from the group.
- When a new member joins and is a **bot**, and the actor is not an admin: the new bot is banned (`ban_chat_member`).

---

## Logging

- `logger.py`: prints to the terminal and writes to `logs/DD-MM-YYYY.log`.
- Command usage, moderation deletes, list matches, errors, and ban events are logged.

---

## Quick reference


| Feature                | Description                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------- |
| Multi-group moderation | Same process; admins resolved per chat via Telegram. `CHAT_ID` is primary + private admin fallback. |
| Message length cap     | From `MSG_LENGTH`.                                                                                  |
| Content-type rules     | From `ALLOWED_TYPES` plus link rules on text/caption.                                               |
| Anti-spam              | Links, phone numbers, `@user`, Telegram entities.                                                   |
| Auto-ban               | 3 moderation events within 30 minutes.                                                              |
| Canned replies         | Files in `list/` matching words members send.                                                       |
| Admin commands         | `/id`, `/reload`, `/ping`, `/help` as above.                                                        |


---

## Technical notes

- Importing `init.bot` from `helpers` creates a circular import; it works because `bot` is defined before `helpers` is imported in `init.py`.
- The bot needs sufficient rights in the group: delete messages, ban members, and send messages.

---

*This file describes the current codebase behavior; update it when you change `init.py` or `helpers.py` if you want the docs to stay accurate.*