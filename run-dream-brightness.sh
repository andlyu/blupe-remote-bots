#!/bin/sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
UI_PYTHON="${YAM_BRIGHTNESS_UI_PYTHON:-$PROJECT_ROOT/codex-runner/.venv/bin/python}"
DREAM_ENV="$PROJECT_ROOT/codex-runner/outputs/dream-brightness/dream-venv"
if [ ! -x "$UI_PYTHON" ]; then
  if [ -n "${YAM_BRIGHTNESS_UI_PYTHON:-}" ]; then
    echo 'YAM_BRIGHTNESS_UI_PYTHON must point to an existing Python environment.' >&2
    exit 1
  fi
  python3 -m venv "$PROJECT_ROOT/codex-runner/.venv"
fi
if ! "$UI_PYTHON" -c 'import PIL, uvicorn, mujoco, numpy, websocket' >/dev/null 2>&1; then
  "$UI_PYTHON" -m pip install -r "$PROJECT_ROOT/codex-runner/requirements.txt"
fi
if [ -z "${YAM_DREAM_PYTHON:-}" ]; then
  if [ ! -x "$DREAM_ENV/bin/python" ]; then
    if ! command -v python3.12 >/dev/null 2>&1; then
      echo 'Install Python 3.12 for Dream SDK 1.0.0, or set YAM_DREAM_PYTHON to its installed environment.' >&2
      exit 1
    fi
    python3.12 -m venv "$DREAM_ENV"
  fi
  if ! "$DREAM_ENV/bin/python" -c 'import dream; assert dream.__version__ == "1.0.0"' >/dev/null 2>&1; then
    "$DREAM_ENV/bin/python" -m pip install dreamlabs==1.0.0 dreamlabs-client==1.0.0
  fi
  YAM_DREAM_PYTHON="$DREAM_ENV/bin/python"
  export YAM_DREAM_PYTHON
fi
export PYTHONDONTWRITEBYTECODE=1
exec "$UI_PYTHON" "$PROJECT_ROOT/codex-runner/integrations/dream-brightness/serve.py" "$@"
