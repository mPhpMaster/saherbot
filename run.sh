#!/usr/bin/env sh
# SaherBot — single Unix helper for the dashboard: toggle background on/off.
# Bot alone (dev): ./venv/bin/python3 main.py   Foreground UI: ./venv/bin/python3 run_dashboard.py start
cd "$(dirname "$0")" || exit 1
if [ -x "./venv/bin/python3" ]; then
  exec ./venv/bin/python3 run_dashboard.py toggle
elif [ -x "./venv/bin/python" ]; then
  exec ./venv/bin/python run_dashboard.py toggle
else
  exec python3 run_dashboard.py toggle
fi
