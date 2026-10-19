"""JSON-lines bridge to an isolated Dream SDK environment. No robot transport."""
import json
import os
from pathlib import Path
import signal
import sys

os.environ['DREAM_LOG'] = 'off'
os.environ.setdefault('LOGURU_LEVEL', 'WARNING')
os.environ.setdefault('JAX_COMPILATION_CACHE_DIR', str(Path(os.environ['DREAM_WORK_DIR']) / 'jax'))


def main():
    import dream
    import numpy as np

    client = dream.DreamClient()
    last_timestamp = None

    def close(*_):
        client.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, close)
    try:
        for line in sys.stdin:
            command = json.loads(line)
            try:
                kind = command['command']
                if kind == 'configure':
                    if dream.__version__ != '1.0.0':
                        raise ValueError('Unsupported Dream SDK version')
                    checkpoint = command['checkpoint']
                    if checkpoint not in ('dreamlabs/dream-1-beta', 'dreamlabs/dream-1-beta-flash'):
                        raise ValueError('Unknown checkpoint')
                    parts = {'right_arm': [0, 6], 'right_gripper': [6, 7],
                             'left_arm': [7, 13], 'left_gripper': [13, 14]}
                    client.policy(dict(checkpoint=checkpoint, robot='yam', strict=True,
                        timeout_ms=15000, action_hz=20, ik={'arm': 'yam', 'head': 'eef', 'solve': 'traj'},
                        embodiment={'state': parts, 'action': dict(parts),
                            'video': {role: 'observation.images.' + role
                                      for role in ('overhead', 'wrist_l', 'wrist_r')}},
                        _record=False))
                    result = {'sdk_version': dream.__version__}
                elif kind == 'reset':
                    client.reset_episode()
                    last_timestamp = None
                    result = {}
                elif kind == 'predict':
                    for tick in command['ticks']:
                        if last_timestamp is not None and tick['timestamp'] <= last_timestamp:
                            continue
                        observation = {key: np.asarray(value, dtype=np.float32) if key.startswith('state.') else value
                                       for key, value in tick['observation'].items()}
                        client.set_observation(tick['frames'], observation, timestamp=tick['timestamp'])
                        last_timestamp = tick['timestamp']
                    action = client.get_action(commanded=command.get('commanded'))
                    result = {'action': action, 'timing': client.last_timing}
                elif kind == 'close':
                    client.close()
                    return
                else:
                    raise ValueError('Unknown worker command')
                response = {'ok': True, 'result': result}
            except Exception as error:
                # Never return exception text, request objects or credential contents.
                response = {'ok': False, 'error_type': type(error).__name__,
                            'code': getattr(error, 'code', None),
                            'reason': getattr(error, 'reason', None),
                            'retry_after_s': getattr(error, 'retry_after_s', None)}
            print(json.dumps(response, default=lambda value: value.tolist(), allow_nan=False), flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
