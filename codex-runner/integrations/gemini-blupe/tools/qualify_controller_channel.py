"""Actual rootless stdio/serializer proof, with no model or physical endpoint."""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import time
import uuid
from unittest.mock import patch


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--runner-root', type=Path, required=True)
    p.add_argument('--workspace-parent', type=Path, required=True)
    p.add_argument('--image', required=True)
    p.add_argument('--mode', choices=('normal','cancel','oversized'), default='normal')
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'backend')); sys.path.insert(0, str(a.runner_root / 'src'))
    from controller_channel import RootlessControllerChannel
    from yam_commands import YamCommands
    from remote_yam import session
    os.environ['GEMINI_SIM_IMAGE'] = a.image
    work = a.workspace_parent / ('channel-proof-' + uuid.uuid4().hex)
    work.mkdir(mode=0o700, parents=True)
    runtime = work / 'controller-runtime'; runtime.mkdir()
    for name in ('controller_entry.py','yam1_environment.py','yam1_scene.py','yam1_kinematics.py'):
        shutil.copy2(root / 'backend' / name, runtime / name)
    shutil.copytree(root / 'assets', work / 'assets')
    for folder in ('models/yam/assets','models/yam_bimanual'):
        shutil.copytree(a.runner_root / folder, work / 'runner' / folder)
    safety = work / 'runner/config/controller-workspaces/native-both-20260929.safety.json'
    safety.parent.mkdir(parents=True)
    shutil.copy2(a.runner_root / 'config/controller-workspaces' / safety.name, safety)
    calibration = json.loads((root / 'tests/fixtures/yam1-calibration.json').read_text())
    config = dict(runner_root='/workspace/runner', gripper_dir='/workspace/assets/linear4310',
                  skills_root='/opt/robotics/plugins/robotics/skills', calibration=calibration)
    (runtime / 'config.json').write_text(json.dumps(config)+'\n')
    controllers = {
        'normal': '''def run(env):
    print("engineering diagnostic on stderr")
    env.left.set_gripper(0., duration_s=.2)
    right = env.right.q_arm.copy()
    right[0] += .005
    env.right.move_joint(right, 1., duration_s=.2)
''',
        'cancel': 'def run(env):\n    while True: pass\n',
        'oversized': 'def run(env):\n    import sys\n    sys.__stdout__.write("x"*20000+"\\n"); sys.__stdout__.flush()\n    while True: pass\n',
    }
    (work / 'controller.py').write_text(controllers[a.mode])
    source_hashes = {name:hashlib.sha256((runtime/name).read_bytes()).hexdigest()
                     for name in ('controller_entry.py','yam1_environment.py','yam1_scene.py','yam1_kinematics.py')}
    source_hashes['controller.py'] = hashlib.sha256((work/'controller.py').read_bytes()).hexdigest()
    source_hashes['host_channel.py'] = hashlib.sha256((root/'backend/controller_channel.py').read_bytes()).hexdigest()
    source_hashes['host_compiler.py'] = hashlib.sha256((root/'backend/yam_commands.py').read_bytes()).hexdigest()
    source_hashes['canonical_validator.py'] = hashlib.sha256((a.runner_root/'src/remote_yam/session.py').read_bytes()).hexdigest()
    channel = RootlessControllerChannel(work, deadline_monotonic=time.monotonic()+40)
    compiler = YamCommands(a.runner_root)
    feedback = dict(source='simulation',observed_at=time.time(),settled=True,homed=True,
                    left_joints_deg=[math.degrees(q) for q in (.12345,1.6,1.2,-1.1,.01234,-.23456)],
                    right_joints_deg=[math.degrees(q) for q in (-.23456,1.4,1.3,-1.2,-.12345,.34567)],
                    left_gripper=.9992793312193716,right_gripper=.412345678)
    api = session.HttpSessionAPI('https://offline.invalid', supports_trajectories=True)
    api._session_capabilities['offline'] = 'synthetic-offline-capability'
    wire, commands = [], []
    def transport(request, **kwargs):
        wire.append(json.loads(request.data)); return io.BytesIO(b'{"offline":true}')
    started = time.monotonic(); cursor = 0; complete = False; rejected = None; ready_s = None
    cancel = threading.Event(); timer = None
    try:
        channel.start(cancel.is_set); ready_s = time.monotonic()-started
        channel.send(dict(kind='begin', observation=feedback))
        if a.mode == 'cancel':
            timer = threading.Timer(.2, cancel.set); timer.start()
        for _ in range(5):
            message = json.loads(channel.receive(cancel.is_set)); commands.append(message)
            if message['kind'] == 'complete': complete=True; break
            if message['kind'] != 'command': raise RuntimeError('Unexpected protocol operation')
            points = compiler.compile(message['payload'], feedback, cursor)
            with patch.object(session.request, 'urlopen', transport):
                api.submit_trajectory('offline','episode','lease','proof-'+str(message['request_id']),10,points)
            cursor += len(points)
            feedback = {**feedback, **points[-1], 'step_id':cursor, 'observed_at':time.time()}
            channel.send(dict(kind='completed',request_id=message['request_id'],observation=feedback))
    except RuntimeError as exc:
        if a.mode == 'normal': raise
        rejected = str(exc)
    finally:
        if timer: timer.cancel()
        channel.close()
    if a.mode == 'normal':
        passed = (complete and len(wire)==2 and wire[0]['waypoints'][-1]['left_gripper']==0.
                  and wire[1]['waypoints'][-1]['right_gripper']==1.
                  and all(p['left_joints_deg']==feedback['left_joints_deg'] for p in wire[0]['waypoints']))
    else:
        expected = 'cancelled or expired' if a.mode=='cancel' else 'exceeded its packet bound'
        passed = not wire and rejected is not None and expected in rejected
    passed = passed and channel.cleanup_confirmed
    report = dict(scope='Actual rootless channel, host compiler and canonical HTTP serializer to a zero-network transport spy',
                  mode=a.mode, passed=passed, physical=False, model_called=False,
                  image=a.image, ready_wall_s=ready_s, wall_s=time.monotonic()-started,
                  packets=len(wire), waypoints=cursor, complete=complete, rejection=rejected,
                  controller='Handwritten engineering proof', commands=commands,
                  cleanup_confirmed=channel.cleanup_confirmed, source_sha256=source_hashes)
    (work / 'controller-protocol-proof.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(receipt=str(work / 'controller-protocol-proof.json'),**report)))
    if not passed: raise SystemExit(1)


if __name__ == '__main__': main()
