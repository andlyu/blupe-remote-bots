"""Read-only baseline verification before integrating either companion patch."""
import hashlib
import json
from pathlib import Path
import sys

bundle = Path(__file__).resolve().parent
name, checkout = sys.argv[1:]
if name not in {'robot-controller', 'session-api'}:
    raise SystemExit('Choose robot-controller or session-api')
manifest = json.loads((bundle / (name + '-baseline.json')).read_text())
patch = bundle / (name + '.patch')
if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest['patch_sha256']:
    raise SystemExit('Patch digest does not match manifest')
failures = []
for entry in manifest['files']:
    path = Path(checkout) / entry['path']
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    if actual != entry['before_sha256']:
        failures.append(entry['path'])
if failures:
    raise SystemExit('Baseline differs; reconcile these files before applying:\n' + '\n'.join(failures))
print('Exact baseline matches; git apply --check can now verify patch context.')
