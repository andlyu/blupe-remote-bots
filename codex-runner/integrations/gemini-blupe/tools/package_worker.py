"""Package public API, canonical controller/recorder and matching task assets."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
p.add_argument('--runner-root',type=Path,default=root.parents[1]);a=p.parse_args()
subprocess.run([sys.executable,str(root/'tools/preflight.py'),'--runner-root',str(a.runner_root)],check=True)
files={str(path.relative_to(root)):path for path in (root/'backend').glob('*.py')}
for name in ('backend/requirements.txt','README.md','docs/YAM1-CONTROLLER-API.md','docs/CONTROLLER-HANDOFF.md','docs/NO-EMAIL-QUEUE.md','docs/PHYSICAL-LIFECYCLE.md'):
    files[name]=root/name
# Ship the same canonical controller/recorder source and public staging assets,
# rather than an incomplete read-only subset or an independently edited copy.
for path in (a.runner_root/'src/remote_yam').rglob('*.py'):
    files['runner/'+str(path.relative_to(a.runner_root))]=path
for directory in ('models/yam/assets','models/yam_bimanual'):
    for path in (a.runner_root/directory).rglob('*'):
        if path.is_file():files['runner/'+str(path.relative_to(a.runner_root))]=path
safety='config/controller-workspaces/native-both-20260929.safety.json'
files['runner/'+safety]=a.runner_root/safety
files['runner/src/remote_yam/ROBOCURVE_LICENSE']=a.runner_root/'src/remote_yam/ROBOCURVE_LICENSE'
files['runner/models/I2RT_LICENSE']=a.runner_root.parent/'models/I2RT_LICENSE'
for path in (root/'assets').rglob('*'):
    if path.is_file():files[str(path.relative_to(root))]=path
manifest=dict(scope='Gemini API with canonical station/session transports',files={})
a.output.parent.mkdir(parents=True,exist_ok=True)
with tarfile.open(a.output,'w:gz') as archive:
    for name,path in sorted(files.items()):
        data=path.read_bytes();manifest['files'][name]=hashlib.sha256(data).hexdigest()
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
        archive.addfile(info,io.BytesIO(data))
    data=(json.dumps(manifest,indent=2)+'\n').encode();info=tarfile.TarInfo('worker-manifest.json');info.size=len(data);info.mode=0o644
    archive.addfile(info,io.BytesIO(data))
print(json.dumps(dict(artifact=str(a.output),files=len(files),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest())))
