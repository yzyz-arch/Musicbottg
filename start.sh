#!/usr/bin/env bash
# Nyalakan bot di background (log: bot.log).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "sudah jalan (PID $(cat bot.pid))"
  exit 0
fi

nohup .venv/bin/python -u bot.py >> bot.log 2>&1 &
echo $! > bot.pid
sleep 3
if kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "✅ jalan (PID $(cat bot.pid)) — tail -f bot.log"
else
  echo "❌ gagal start, cek bot.log"; rm -f bot.pid; exit 1
fi
