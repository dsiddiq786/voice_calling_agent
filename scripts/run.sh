#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test -x .venv/bin/uvicorn || ./scripts/setup.sh
NOMNOSH_PORT="${NOMNOSH_PORT:-8000}"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$NOMNOSH_PORT" --reload
