# SaherBot

Telegram group moderation bot with a **local web dashboard** (FastAPI): monitored chats, auto-replies, backups, events, and **start/stop/restart** for the bot from the UI.

## Requirements

- **Python 3.12+** (on Windows, `install.bat` can install Python via `winget` if it is missing.)
- Dependencies are listed in [`requirements.txt`](requirements.txt) and installed by the setup scripts.

## Quick start (recommended)

1. **Get the code** — `git clone https://github.com/mPhpMaster/saherbot.git` **or** download the [`main` branch ZIP](https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip) and extract it.
2. **Install** — From the project root: **Windows:** `install.bat` · **Linux/macOS:** `./install.sh`
3. **Configure** — `install.bat` / `./install.sh` can prompt for **`.env`** (or copy `.env.example` and run them again, answer **Y** to reconfigure). Then set **bot token** and **primary chat** in the dashboard. See [DOCUMENTATION.md](DOCUMENTATION.md).
4. **Run the dashboard** — **Windows:** **`run.bat`** toggles the dashboard in the background. For a **foreground** server in this window: `venv\Scripts\python.exe run_dashboard.py start`. **Linux/macOS:** **`./run.sh`** toggles (`install.sh` marks it executable); foreground: `./venv/bin/python3 run_dashboard.py start`.
5. Open `http://127.0.0.1` (default **port 80** when `DASHBOARD_PORT` is unset or empty; change `DASHBOARD_HOST` / `DASHBOARD_PORT` in `.env` if needed), sign in, then **start the bot** from the **navbar** on the dashboard home.

For normal use, toggle the **dashboard** with **`run.bat`** (Windows) or **`./run.sh`** (Linux/macOS), then open the UI. To run the **bot process alone** for development (no dashboard), use **`venv\Scripts\python.exe main.py`** or **`./venv/bin/python3 main.py`**.

**Without Git (ZIP):** [SETUP_WITHOUT_GIT.md](SETUP_WITHOUT_GIT.md). **One-step download + install next to a script:** use `download-and-install.bat` from the repo (see that file’s comments).

**Remove the app:** `uninstall.bat` or `./uninstall.sh` — they create a mandatory backup under `data/backups/` before deleting `venv` and cleaning up.

Full behavior, environment variables, and Telegram commands: **[DOCUMENTATION.md](DOCUMENTATION.md)**.

## Copyright and license

Copyright © 2023 hlaCk (https://github.com/mPhpMaster/saherbot)

Licensed under the [MIT License](https://github.com/mPhpMaster/saherbot/blob/master/LICENSE).
