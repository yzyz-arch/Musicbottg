#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  kill "$(cat bot.pid)"
  echo "⏹ stopped (PID $(cat bot.pid))"
else
  pkill -f "musicem-bot/.venv/bin/python -u bot.py" 2>/dev/null || true
  echo "⏹ tidak ada proses / sudah berhenti"
fi
rm -f bot.pid
