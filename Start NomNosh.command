#!/bin/zsh
set -e

PROJECT_DIR="/Users/mac/Documents/Codex/2026-07-19/bu"
export NOMNOSH_PORT=8010
cd "$PROJECT_DIR"

clear
echo "Starting NomNosh Voice Order MVP..."
echo "Keep this window open while using Fatima."
echo

# Always replace any stale development server so new voice code and .env keys load.
PORT_PIDS=(${(f)"$(lsof -tiTCP:$NOMNOSH_PORT -sTCP:LISTEN 2>/dev/null)"})
if (( ${#PORT_PIDS[@]} )); then
  echo "Closing old NomNosh server..."
  kill $PORT_PIDS 2>/dev/null || true
  sleep 2
fi

if [[ ! -x .venv/bin/uvicorn ]]; then
  ./scripts/setup.sh
fi

(sleep 2; open "http://127.0.0.1:$NOMNOSH_PORT/customer") &
./scripts/run.sh
