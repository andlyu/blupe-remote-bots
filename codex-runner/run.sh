#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# Use an explicitly selected Python environment when supplied.
if [ -n "${YAM_RUNNER_PYTHON:-}" ]; then
  exec "$YAM_RUNNER_PYTHON" "$PROJECT_ROOT/run.py" "$@"
fi
VENV="$PROJECT_ROOT/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi

if ! "$VENV/bin/python" -c 'import mujoco, numpy, websocket, uvicorn, sentence_transformers' >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$PROJECT_ROOT/requirements.txt"
fi

exec "$VENV/bin/python" "$PROJECT_ROOT/run.py" "$@"
