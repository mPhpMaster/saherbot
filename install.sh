#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 1
fi
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
mkdir -p logs list data data/backups

DO_ENV=0
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
  DO_ENV=1
elif [ -f .env ]; then
  echo ".env already exists (not overwritten)."
  printf "Configure required .env variables now? (y/N): "
  read -r REC
  case "$REC" in y|Y) DO_ENV=1 ;; *) ;; esac
fi

if [ "$DO_ENV" = 1 ]; then
  echo ""
  echo "--- Interactive .env ---"
  ./venv/bin/python3 scripts/write_install_env.py
fi

chmod +x run.sh 2>/dev/null || true

echo ""
echo "Done."
echo "Toggle dashboard (start if stopped, stop if running):  ./run.sh"
echo "Foreground dashboard:  ./venv/bin/python3 run_dashboard.py start"
echo "Bot (developers):  ./venv/bin/python3 main.py"
echo "Normal use: open the dashboard, set token and chats, then start the bot from the UI."
