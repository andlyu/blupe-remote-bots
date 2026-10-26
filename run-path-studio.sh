#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv-path-studio/bin/python ]; then
  echo 'Set up Path Studio once:' >&2
  echo '  python3.12 -m venv .venv-path-studio' >&2
  echo '  .venv-path-studio/bin/pip install -r codex-runner/path-studio-requirements.txt' >&2
  exit 1
fi
exec .venv-path-studio/bin/python codex-runner/path_studio.py "$@"
