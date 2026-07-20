#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test -x .venv/bin/pytest || ./scripts/setup.sh
exec .venv/bin/pytest -q

