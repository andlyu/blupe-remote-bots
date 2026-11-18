"""Package only public API/docs and unchanged canonical read transports."""
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
for name in ('README.md','docs/YAM1-CONTROLLER-API.md','docs/CONTROLLER-HANDOFF.md'):
    files[name]=root/name
for name in ('__init__.py','session.py','cadence.py','cameras.py'):
    files['runner/src/remote_yam/'+name]=a.runner_root/'src/remote_yam'/name
manifest=dict(scope='Gemini API with canonical read-only station transport',files={})
a.output.parent.mkdir(parents=True,exist_ok=True)
with tarfile.open(a.output,'w:gz') as archive:
    for name,path in sorted(files.items()):
        data=path.read_bytes();manifest['files'][name]=hashlib.sha256(data).hexdigest()
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
        archive.addfile(info,io.BytesIO(data))
    data=(json.dumps(manifest,indent=2)+'\n').encode();info=tarfile.TarInfo('worker-manifest.json');info.size=len(data);info.mode=0o644
    archive.addfile(info,io.BytesIO(data))
print(json.dumps(dict(artifact=str(a.output),files=len(files),sha256=hashlib.sha256(a.output.read_bytes()).hexdigest())))
