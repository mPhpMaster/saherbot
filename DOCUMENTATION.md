# SaherBot documentation — what does the bot do?

A Telegram bot built with Python (`pyTelegramBotAPI`) to manage a specific group: auto-replies from files or the dashboard database, content moderation, and bans on repeated violations. The bot is intended to run mainly in a **group** (private chats are not moderated for normal messages).

**Recommended operation:** run `install.bat` / `./install.sh` once (they can prompt for **`.env`** values). Toggle the **dashboard** with **`run.bat`** (Windows) or **`./run.sh`** (Linux/macOS): if it is running it stops; if stopped it starts in the background. Sign in, set bot token and chats in the UI, then start the bot from the **navbar** on the home dashboard. For development only, run the bot alone with **`venv\Scripts\python.exe main.py`** (Windows) or **`./venv/bin/python3 main.py`** (Linux/macOS).

---

## Startup

- Entry point: `main.py` → reads **bots** with tokens from the database → one OS thread per bot → `register_handlers` / `infinity_polling()`.
- The Telegram token and all moderation/reply settings are read from **`global_settings`**, **`chats`**, and **`auto_replies`** in the database (configured in the dashboard). **`loader.py`** only holds static lists and flags (`USE_DASHBOARD_CHATS` / `USE_DASHBOARD_REPLIES` are always on in code).
- On startup the `list/` folder is loaded (`helpers.load_lists()`), then `bot.infinity_polling()` starts (retries on Telegram **502/503** and short outages).

---

## Configuration: dashboard vs `.env`

| What you want to change | Where to set it |
| ------------------------ | ---------------- |
| **Bot token**, **primary chat ID**, **notify on startup** | Dashboard **Bots** (`bots` table). |
| **Which groups are moderated**, per-chat length/echo | Dashboard **Chats** (`chats` table). If **no** chat has moderation enabled, the bot moderates **no** groups. |
| **Auto-replies** | Dashboard **per chat**: open **Chats** → **ردود** (or `/chats/{chat_id}/replies`), then **`list/`** files as fallback when no DB row matches. Legacy global-only `auto_replies` rows are migrated on startup (see `bootstrap.py`). |
| **Dashboard login**, bind address/port | **`.env`**: `DASHBOARD_PASSWORD`, optional `DASHBOARD_SECRET`, `DASHBOARD_HOST`, `DASHBOARD_PORT` (defaults to **80** when unset or empty). |
| **Database file / server** | **`.env`**: `DB_TYPE`, `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, `DB_DATABASE` (see `.env.example`). Default SQLite file `data/saherbot.db` when `DB_TYPE=sqlite` and `DB_DATABASE` is empty. |

**`.env` does not** define `BOT_TOKEN`, `CHAT_ID`, `MONITORED_CHAT_IDS`, `MSG_LENGTH`, `NOTIFY_RUN`, `ECHO_COMMAND`, or `USE_DASHBOARD_*` anymore.

---

## Environment variables (`.env`) — reference

Read by `python-decouple` in `dashboard/app.py`, `run_dashboard.py`, and `saherbot_db/database.py` (not by `loader.py`).


| Variable             | Meaning                                                                                                                                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`       | Optional **legacy** full SQLAlchemy URL. If non-empty, **`DB_*` variables are ignored**. If empty, the URL is built from `DB_TYPE` and related fields (see `.env.example`).                                                                                        |
| `DB_TYPE`            | Used when `DATABASE_URL` is empty: `sqlite` (default), `postgresql`, or `mysql`. The SQLAlchemy URL is built from `DB_TYPE` and the other `DB_*` fields (see `.env.example`).                                                                                                                           |
| `DB_HOST` / `DB_PORT` / `DB_USERNAME` / `DB_PASSWORD` / `DB_DATABASE` | Used for client/server databases. For **SQLite**, only `DB_DATABASE` matters (path to `.db`, relative to project root or absolute); if empty, the default file is `data/saherbot.db`. Others are ignored for SQLite. PostgreSQL default port **5432**, MySQL **3306** if `DB_PORT` is empty. |
| `DASHBOARD_PASSWORD` | Required to use the local web UI (`run_dashboard.py`). Plain password for the login form.                                                                                                                                                                         |
| `DASHBOARD_SECRET`   | Optional. Secret for signing the session cookie; if empty, `DASHBOARD_PASSWORD` is used (ensure it is long enough in production).                                                                                                                                   |
| `DASHBOARD_HOST`     | Optional. Bind address for the dashboard (default `127.0.0.1`).                                                                                                                                                                                                      |
| `DASHBOARD_PORT`     | Optional. Port for the dashboard; **default 80** when unset or empty (binding to port 80 on Linux/macOS may require elevated privileges).                                                                                                                            |


Allowed content types for filtering are defined in `loader.py` as `ALLOWED_TYPES`: text, photo, voice, video, audio.

### Web dashboard (local)

- Run or stop the **dashboard** in the background with **`run.bat`** (Windows) or **`./run.sh`** (Linux/macOS) from the project root — they run `python run_dashboard.py toggle` (start if stopped, stop if running). For a **foreground** server in the current terminal, run **`venv\Scripts\python.exe run_dashboard.py start`** (Windows) or **`./venv/bin/python3 run_dashboard.py start`** (Linux/macOS).
- When the app loads, it writes **`data/dashboard.pid`** so uninstall and `run_dashboard.py stop` can find the process.
- Optional CLI: **`python run_dashboard.py stop`** stops the dashboard using `data/dashboard.pid`; **`python run_dashboard.py status`** prints whether that PID is running.
- Sign in with **`DASHBOARD_PASSWORD`**. The **home** page (`/`) is the **dashboard** (stats, recent events, global descriptions). Set **bot token**, **primary chat ID**, and per-bot options under **Bots**; add chats under **Chats** or from a bot’s edit page; **auto-replies** are managed per chat at **`/chats/{chat_id}/replies`**. Toggling moderation updates the bot **without** a full restart (via `chats_config_revision`).
- **Start / stop / restart** for the **bot** from the **top navbar** uses `data/bot.pid` and OS-specific signals / `taskkill` on Windows. With JavaScript enabled, those actions use **`Accept: application/json`** and show a **desktop notification** (Arabic title) while refreshing the status badge. **`GET /api/bot-status`** (session-authenticated) returns JSON for the live status badge.
- The backup page can create ZIP backups and restore a selected ZIP from `data/backups/`. Stop the bot first; restore replaces `data/saherbot.db` and `list/` files contained in the archive.
- The events page (`/events`) shows the latest 100 rows from the `events` table and can filter by event type or chat ID.
- Do **not** rely on a single helper script that launches both the bot and the dashboard in two windows. Start the dashboard first (`run.bat` / `./run.sh` or foreground `run_dashboard.py start`), then start the bot from the **navbar**.

### Install / uninstall

- Windows: run `install.bat`. It creates `venv\`, installs packages, and ensures `logs\`, `list\`, and `data\` exist. On a **new** `.env` from `.env.example`, or if you answer **Y** to reconfigure when `.env` already exists, it runs **`scripts/write_install_env.py`** to prompt for `DASHBOARD_PASSWORD` and related keys.
- Linux/macOS: run `./install.sh` (same behaviour; sets **`chmod +x run.sh`** when possible).
- Uninstall on Windows: run `uninstall.bat`.
- Uninstall on Linux/macOS: run `./uninstall.sh`.
- Both uninstall scripts ask for confirmation, try to stop the bot from `data/bot.pid` and the dashboard from `data/dashboard.pid`, then create a mandatory backup before deleting anything.
- The uninstall backup is written to `data/backups/uninstall-YYYYMMDD-HHMMSS.zip` and includes `data/saherbot.db` if present, the `list/` folder contents, and `manifest.json`. `.env` is excluded by default and is included only after a second explicit confirmation because it may contain secrets.
- If backup creation fails, uninstall exits without removing `venv\` / `venv/` or cleaning `data\` / `data/`.

### Multiple groups (same bot)

- Add the **same** bot to another group/supergroup and give it the same admin rights (delete messages, ban, etc.).
- **Do not** run a second `python main.py` with the **same** token (Telegram allows only one active session per bot token).
- Rules, DB or `list/` replies, strikes, and “who is admin” apply **per chat** using `message.chat.id`.
- Set the **primary chat ID** and **notify on startup** in the **dashboard**; private `/id` and admin checks in DM use that primary context from the database.
- To watch **only** specific groups, enable moderation only on the desired rows in **Dashboard → Chats**.

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

For users who are **not** administrators of the **current** group:

1. **Text length**: If the message is text and longer than the effective limit, it is deleted with a request to shorten (`delete_with_mention`). The effective limit comes from the current `chats` row (`msg_max_length`, `msg_length_unlimited`) over `global_settings` defaults.
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

- The bot checks enabled rows in `auto_replies` **for the current chat only** (`chat_id` must match the group).
- The dashboard prevents duplicate enabled triggers **within the same chat** at create/edit time; there is no database-level uniqueness constraint yet.
- Each file under `list/` becomes a **key** named like the file (e.g. `list/الدبل` → key `الدبل`).
- If a member sends text that matches the file name (case-insensitive):
  - If the value is a **string** (`str`): the bot replies with that text.
  - If the value has a `**path`**: the file is treated as an image and sent as a photo with `reply_to` the message.
- `load_lists()` behavior:
  - Try to read the file as text; on failure it is treated as binary and the path is stored for photo sending.
  - If text content starts with `-`, **everything after the first two characters** is the reply (e.g. a line `-` then a link).
  - Otherwise the code stores a list containing the file path; with the current handler this may not produce a text/photo reply and may fall through to `echo_command` if enabled.

If the text matches no DB/file reply and the message is valid plain text (no full-line URL), `echo_command` uses the current chat row’s `echo_enabled` over `global_settings.default_echo_enabled`.

---

## Member events

- On `new_chat_members` or `left_chat_member`: the system message is always deleted from the group.
- When a new member joins and is a **bot**, and the actor is not an admin: the new bot is banned (`ban_chat_member`).

---

## Logging

- `logger.py`: prints to the terminal and writes to `logs/DD-MM-YYYY.log` (dashboard actions and bot process both use the same `log()` where wired).
- Command usage, moderation deletes, list matches, errors, and ban events are logged.

---

## Quick reference


| Feature                | Description                                                                                         |
| ---------------------- | --------------------------------------------------------------------------------------------------- |
| Multi-group moderation | Same process; admins resolved per chat via Telegram. Primary + private-admin context from **dashboard** / DB (`primary_chat_id`). |
| Message length cap     | From **dashboard** / DB (`chats` / `global_settings`). |
| Content-type rules     | From `ALLOWED_TYPES` plus link rules on text/caption.                                               |
| Anti-spam              | Links, phone numbers, `@user`, Telegram entities.                                                   |
| Auto-ban               | 3 moderation events within 30 minutes.                                                              |
| Canned replies         | **Dashboard** `auto_replies` **per chat** (`/chats/{id}/replies`); else files in `list/`.                                    |
| Admin commands         | `/id`, `/reload`, `/ping`, `/help` as above.                                                        |


---

## Technical notes

- Importing `init.bot` from `helpers` creates a circular import; it works because `bot` is defined before `helpers` is imported in `init.py`.
- The bot needs sufficient rights in the group: delete messages, ban members, and send messages.

---

*This file describes the current codebase behavior; update it when you change `init.py` or `helpers.py` if you want the docs to stay accurate.*