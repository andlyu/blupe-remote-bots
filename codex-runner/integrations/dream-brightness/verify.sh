#!/bin/sh
# Required offline release preflight. Use a retained copy of the deployed validator.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$HERE/../.." && pwd)
UI_PYTHON="${YAM_BRIGHTNESS_UI_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
: "${YAM_DREAM_RUNNER_ROOT:?Set the exact Dream-capable runner source directory}"
: "${YAM_CANONICAL_TRAJECTORY:?Set the canonical validator copied from the tested deployment}"
"$UI_PYTHON" - "$YAM_DREAM_RUNNER_ROOT" "$YAM_CANONICAL_TRAJECTORY" <<'PY'
import hashlib, pathlib, subprocess, sys
root, validator = map(lambda value: pathlib.Path(value).resolve(), sys.argv[1:])
git_root = subprocess.run(['git','-C',str(root),'rev-parse','--show-toplevel'],text=True,capture_output=True)
if git_root.returncode == 0 and pathlib.Path(git_root.stdout.strip()) / 'codex-runner' == root:
    print('Dream runner revision:', subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip())
else:
    print('Dream runner revision: source snapshot; retain its archive/base receipt separately')
digest = hashlib.sha256()
for path in sorted((root / 'src/remote_yam').glob('*.py')):
    digest.update(path.name.encode()); digest.update(path.read_bytes())
print('Dream runner module digest:', digest.hexdigest())
print('Canonical validator SHA256:', hashlib.sha256(validator.read_bytes()).hexdigest())
PY
"$UI_PYTHON" -m pytest "$HERE/test_brightness.py" "$HERE/test_comparison.py" "$HERE/test_command_contract.py" "$YAM_DREAM_RUNNER_ROOT/tests/test_dream_calibration.py" -q -p no:cacheprovider "$@"
node --test "$HERE/test_brightness_ui.cjs"
