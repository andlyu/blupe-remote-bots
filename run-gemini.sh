#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNNER="$PROJECT_ROOT/codex-runner"
VENV="$RUNNER/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
if ! "$VENV/bin/python" -c 'import mujoco, numpy, websocket, uvicorn' >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$RUNNER/requirements.txt"
fi
exec "$VENV/bin/python" "$RUNNER/gemini_playground.py" "$@"
