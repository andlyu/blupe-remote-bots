"""Required offline RoboHarness release gate; never creates a robot session."""
import argparse
import hashlib
import importlib.metadata
import io
import json
import shutil
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parent
SOURCES=['roboharness_playground.py','roboharness_preflight.py','roboharness_broker_preflight.py','playground.py','multi_robot.py',
    'requirements-roboharness.txt','config/roboharness-linear4310-reference.json','models/yam_bimanual/scene.xml','models/yam_bimanual/yam_bimanual.xml']


def source_inventory():
    return SOURCES+[str(p.relative_to(ROOT)) for pattern in
        ('src/remote_yam/*.py','config/controller-workspaces/*.json','tests/test_roboharness_*.py','tests/fixtures/roboharness-*.json','tests/fixtures/roboharness-*.png')
        for p in sorted(ROOT.glob(pattern))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-dirty',action='store_true',help='Draft checks only; cannot authorize a deployment')
    args=parser.parse_args()
    started=time.time();tick=time.perf_counter()
    sys.path[:0]=[str(ROOT/'src'),str(ROOT),str(ROOT/'tests')]
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_roboharness_*.py')
    output=io.StringIO();result=unittest.TextTestRunner(stream=output,verbosity=2).run(suite)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    versions={}
    for name in ['mujoco','numpy','scipy','opencv-python-headless','pillow','websocket-client']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]='not installed under this distribution name'
    sources=source_inventory()
    status='passed' if result.wasSuccessful() and result.testsRun>=70 and not dirty else 'draft_passed' if result.wasSuccessful() and result.testsRun>=70 else 'failed'
    receipt=dict(status=status,scope='offline command contract; no physical execution',started_at=started,
        duration_s=time.perf_counter()-tick,source_revision=revision,dirty_source=dirty,tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),dependencies=versions,
        external_programs={'ffmpeg':subprocess.check_output([shutil.which('ffmpeg'),'-version'],text=True).splitlines()[0]} if shutil.which('ffmpeg') else {},
        source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        command='PYTHONPATH=codex-runner/src:codex-runner python codex-runner/roboharness_preflight.py --output <receipt.json>',
        output=output.getvalue(),robot_sessions=0,actuator_submissions=0)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(output.getvalue());print(json.dumps({k:receipt[k] for k in ['status','tests_run','duration_s','source_revision','dirty_source']}))
    return 0 if status=='passed' or args.allow_dirty and status=='draft_passed' else 1


if __name__=='__main__':raise SystemExit(main())
