"""Prepare a secret-free immutable image context from exact shared inputs."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--runner-root',type=Path,default=root.parents[1])
parser.add_argument('--output',type=Path,required=True)
args = parser.parse_args()

def constants(file):
    result = {}
    for node in ast.parse(file.read_text()).body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            try:result[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError,TypeError):pass
    return result

scene = constants(root/'backend/yam1_scene.py')
context = args.output
context.mkdir(parents=True,exist_ok=False)
manifest = dict(scope='YAM1 adapted common-controller runtime; contact qualification pending',
                variant='yam1', files={})

def copy(source, relative, expected=None):
    data = source.read_bytes(); digest = hashlib.sha256(data).hexdigest()
    if expected is not None and digest != expected:
        raise SystemExit('Pinned image input changed: '+str(source.name))
    output = context/relative;output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(data);manifest['files'][relative] = digest

modules = ('simulation_entry.py','reference_simulation_entry.py','yam1_simulation_entry.py',
           'yam1_simulation.py','yam1_scene.py','yam1_kinematics.py','yam1_environment.py',
           'yam_commands.py','controller_entry.py')
for name in modules:copy(root/'backend'/name,name)
copy(root/'backend/Containerfile','Containerfile')
for name in ('__init__.py','session.py','cadence.py'):
    copy(args.runner_root/'src/remote_yam'/name,'station-runner/src/remote_yam/'+name)
for name,digest in scene['ARM_ASSETS'].items():
    copy(args.runner_root/'models/yam/assets'/name,'station-runner/models/yam/assets/'+name,digest)
for name,digest in (('yam_bimanual.xml',scene['MODEL_SHA256']),('scene.xml',scene['SCENE_SHA256'])):
    copy(args.runner_root/'models/yam_bimanual'/name,'station-runner/models/yam_bimanual/'+name,digest)
copy(args.runner_root/'config/controller-workspaces/native-both-20260929.safety.json',
     'station-runner/config/controller-workspaces/native-both-20260929.safety.json',scene['SAFETY_SHA256'])
for name,digest in scene['GRIPPER_ASSETS'].items():
    copy(root/'assets/linear4310'/name,'station-assets/linear4310/'+name,digest)
copy(root/'assets/linear4310/linear_4310.xml','station-assets/linear4310/linear_4310.xml',scene['INSTALLED_SHA256'])
for name in ('LICENSE','PROVENANCE.md'):
    copy(root/'assets/linear4310'/name,'station-assets/linear4310/'+name)
(context/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(output=str(context),variant='yam1',files=len(manifest['files']))))
