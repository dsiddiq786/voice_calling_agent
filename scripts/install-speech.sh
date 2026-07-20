#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test -x .venv/bin/pip || ./scripts/setup.sh
.venv/bin/pip install -r requirements-speech.txt
echo "Local speech recognition installed. The model downloads on first use."

