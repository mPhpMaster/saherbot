"""Interactive write of SaherBot `.env` during install (dashboard + database)."""

from __future__ import annotations

from pathlib import Path


def _validate_port(s: str) -> bool:
    try:
        p = int(s)
        return 1 <= p <= 65535
    except ValueError:
        return False


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    print("")
    print("=== SaherBot: required .env values ===")
    print("(Bot token and chats are set later in the web dashboard.)")
    print("")
    while True:
        pw = input("DASHBOARD_PASSWORD (required for web login): ").strip()
        if pw:
            break
        print("  Password cannot be empty.")
    secret = input("DASHBOARD_SECRET (optional, Enter to skip): ").strip()
    print("")
    print("Database: default SQLite data/saherbot.db (edit DB_* in .env for Postgres/MySQL).")
    host = input("DASHBOARD_HOST [127.0.0.1]: ").strip() or "127.0.0.1"
    while True:
        port_raw = input("DASHBOARD_PORT [80]: ").strip() or "80"
        if _validate_port(port_raw):
            break
        print("  Port must be a number between 1 and 65535.")

    lines = [
        "# SaherBot — written by install (scripts/write_install_env.py)",
        "",
        "# Database (see .env.example)",
        "DB_TYPE=sqlite",
        "DB_HOST=127.0.0.1",
        "DB_PORT=",
        "DB_USERNAME=",
        "DB_PASSWORD=",
        "DB_DATABASE=data/saherbot.db",
        "",
        "# Web dashboard",
        f"DASHBOARD_PASSWORD={pw}",
        f"DASHBOARD_SECRET={secret}",
        f"DASHBOARD_HOST={host}",
        f"DASHBOARD_PORT={port_raw}",
        "",
        "# Bot token, primary chat, chats, replies: set in the dashboard UI.",
    ]
    text = "\n".join(lines) + "\n"
    env_path.write_text(text, encoding="utf-8")
    print("")
    print(f"Wrote: {env_path}")
    print("")
    print("Start / stop the dashboard (toggle):")
    print("  Windows:  run.bat")
    print("  Linux/mac:  chmod +x run.sh && ./run.sh")
    print("Or run in this terminal:  python run_dashboard.py start")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
