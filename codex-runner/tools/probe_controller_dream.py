#!/usr/bin/env python3
"""One real Dream One prediction on the controller, with no command transport."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from remote_yam.cameras import CameraFrameSource
from remote_yam.controller_dream import LoopbackControllerInputs
from remote_yam.dream_policy import DreamAdapter, DreamWorker, MODELS
from remote_yam.dream_worker_pool import DreamWorkerPool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--credentials', required=True)
    parser.add_argument('--sdk-python', required=True)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--provider', choices=MODELS, default='dream')
    parser.add_argument('--prompt', default='Hold the current pose.')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config.get('hardware') != 'yam':
        parser.error('Require a YAM controller profile')
    inputs = LoopbackControllerInputs(robot_id=config['robot_id'], cameras=config['cameras'])
    args.work_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(args.work_dir, 0o700)
    stop = threading.Event()
    deadline = threading.Timer(170, stop.set)
    deadline.daemon = True
    began = time.monotonic()
    receipt = dict(started_at=datetime.now(timezone.utc).isoformat(), robot_id=config['robot_id'],
        checkpoint=MODELS[args.provider][0], execution_location='controller',
        state_route='loopback_native_operator', image_route='loopback_existing_camera_relay',
        command_clients_created=0, commands_submitted=0, predictions=0,
        phases=[], camera_sets=[], result='in_progress')

    def save():
        path = args.work_dir / 'receipt.json'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(receipt, stream, allow_nan=False, indent=2)

    class Cameras:
        source = CameraFrameSource('http://127.0.0.1:8089')

        def capture_for_policy(self, observation, **kwargs):
            frames = self.source.capture_for_policy(observation, **kwargs)
            receipt['camera_sets'].append([frame.summary() for frame in frames])
            receipt['camera_sets'] = receipt['camera_sets'][-12:]
            return frames

    class Worker(DreamWorker):
        def call(self, command, **kwargs):
            if command == 'predict':
                if receipt['predictions']:
                    raise RuntimeError('One-prediction budget exhausted')
                inputs()  # Confirm native state is still initialized and idle.
                receipt['predictions'] += 1
            started = time.monotonic()
            reply = super().call(command, **kwargs)
            receipt['phases'].append(dict(phase=command, duration_s=time.monotonic()-started,
                ok=reply['ok'], stage_timings=reply.get('stage_timings', [])))
            if not reply['ok']:
                receipt['failure'] = {key: reply.get(key) for key in (
                    'error_type', 'code', 'reason', 'phase', 'protocol_category', 'http_status',
                    'cause_type', 'transport_stage', 'timing')}
            save()
            return reply

    adapter = pool = None
    try:
        inputs()  # Fail before SDK preparation if actual measured input is absent.
        deadline.start()
        pool = DreamWorkerPool(args.sdk_python, args.credentials, args.work_dir/'worker', worker_factory=Worker)
        pool.prime(timeout=145)
        adapter = DreamAdapter(provider=args.provider, model=receipt['checkpoint'],
            credentials=args.credentials, python=args.sdk_python, directory=args.work_dir/'worker',
            robot_id=config['robot_id'], observation_source=inputs,
            camera_source=Cameras(), gateway_max_step_deg=9, worker_factory=pool.factory)
        adapter.cancelled = stop.is_set
        points = adapter.build_trajectory(args.prompt, inputs(), 0)
        inputs()
        receipt.update(result='real_prediction_converted_without_submission',
            waypoint_count=len(points), probe=adapter.last_probe, state_read=inputs.last_read)
    except Exception as error:
        receipt.update(result='failed', error_type=type(error).__name__)
        if str(error) in {'Live probe requires initialized idle physical feedback',
                          'Controller measured joints are unavailable',
                          'Controller robot identity is unavailable or changed',
                          'One-prediction budget exhausted'}:
            receipt['condition'] = str(error)
    finally:
        stop.set()
        deadline.cancel()
        if adapter is not None:
            adapter.close_transport()
        if pool is not None:
            pool.close()
        receipt.update(ended_at=datetime.now(timezone.utc).isoformat(),
            total_s=time.monotonic()-began,
            source_sha256={name: hashlib.sha256((Path(__file__).resolve().parents[1]/'src/remote_yam'/name).read_bytes()).hexdigest()
                for name in ('controller_dream.py', 'dream_policy.py', 'dream_worker.py')})
        save()
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['result'] == 'real_prediction_converted_without_submission' else 1


if __name__ == '__main__':
    raise SystemExit(main())
