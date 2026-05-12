#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
if [ -x "venv/bin/python" ]; then
  exec venv/bin/python scripts/saherbot_uninstall.py "$@"
else
  exec python3 scripts/saherbot_uninstall.py "$@"
fi
