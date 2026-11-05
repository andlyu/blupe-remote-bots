"""Actual worker protocol/cache proof; no observations, predictions or robot actions."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk-python', type=Path, required=True)
parser.add_argument('--credentials-file', type=Path, required=True)
parser.add_argument('--state-root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--runner-name', required=True)
args = parser.parse_args()
if not args.runner_name.strip(): parser.error('Confirmed runner name is required')
SOURCE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SOURCE / 'src')]
from remote_yam.api_depth import ApiDepth
from remote_yam.cameras import CameraFrameSource
from remote_yam.dream_calibration import ROBOHOUSE, binding_from_report, kinematic_description
from remote_yam.dream_policy import DreamAdapter, DreamWorker
PUBLIC_STATE = args.state_root.resolve()
PUBLIC_STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
os.environ['JAX_COMPILATION_CACHE_DIR'] = str(PUBLIC_STATE / 'jax')
BACKEND = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'
SDK, CREDENTIALS = args.sdk_python, args.credentials_file
receipts = []

for index in range(2):
    api = ApiDepth(BACKEND, ROBOHOUSE)
    try: report = json.loads(api.read('/calibration', 256_000))
    finally: api.connection.close()
    binding = binding_from_report(report, ROBOHOUSE)
    description = kinematic_description(binding)
    directory = PUBLIC_STATE / ('deployment-preparation-' + str(index))
    worker = DreamWorker(SDK, CREDENTIALS, directory)
    provider = None
    started = time.monotonic()
    print('Preparing actual SDK worker', index + 1, flush=True)
    try:
        prime = worker.call('prime', checkpoints=['dreamlabs/dream-1-beta'],
            kinematics=description, timeout=360)
        assert prime['ok'] and prime['result']['fully_ready'] is True, prime
        provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
            credentials=CREDENTIALS, python=SDK, directory=directory,
            camera_source=CameraFrameSource(BACKEND), observation_source=lambda:None,
            worker_factory=lambda *args:worker, robot_id=ROBOHOUSE)
        provider.configure_robot_workspace(ROBOHOUSE, report=report)
        provider.start_preparation(lambda:False)
        provider.wait_ready(lambda:False)
        assert provider._ready.is_set() and provider._failure is None
        receipts.append(dict(worker=index + 1, sdk_version=prime['result']['sdk_version'],
            actual_trajectory_ready=prime['result']['fully_ready'],
            adapter_confirmed_calibration=provider.public_config()['kinematic_calibration'],
            trajectory_variants=prime['result'].get('trajectory_variants'),
            elapsed_s=time.monotonic()-started,
            stage_timings=prime.get('stage_timings', [])))
        print('Worker', index + 1, 'confirmed actual nested calibration receipt;',
              round(receipts[-1]['elapsed_s'], 3), 'seconds', flush=True)
    finally:
        if provider is not None: provider.close_transport()
        else: worker.close()

result = dict(verified_at=datetime.now(timezone.utc).isoformat(), runner_name=args.runner_name.strip(),
    execution_mode='deployment SDK configuration and local solver preparation',
    checkpoint='dreamlabs/dream-1-beta', inference_requests=0, observations_sent=0,
    robot_queue_entries=0, physical_commands=0,
    metadata_access='Existing Dream SDK configured model metadata service; no prediction',
    workers=receipts)
args.output.write_text(json.dumps(result, indent=2)+'\n')
print('Saved', args.output, flush=True)
