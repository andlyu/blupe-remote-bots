"""JSON-lines bridge to an isolated Dream SDK environment. No robot transport."""
import json
import math
import os
from pathlib import Path
import signal
import sys

os.environ['DREAM_LOG'] = 'off'
os.environ.setdefault('LOGURU_LEVEL', 'WARNING')
os.environ.setdefault('JAX_COMPILATION_CACHE_DIR', str(Path(os.environ['DREAM_WORK_DIR']) / 'jax'))

# Emit documented status fields, never arbitrary server text or identifiers.
ERROR_CODES = {'DA-0000', 'DA-0001', 'DA-1000', 'DA-2000', 'DA-4000', 'DA-5000', 'DA-6000',
               'not_found', 'conflict', 'invalid_request', 'validation', 'invalid_api_key', 'forbidden'}
ERROR_REASONS = {'pool_warming', 'rate_limited', 'pool_full', 'queue_timeout', 'max_serves',
                 'cannot_scale', 'missing', 'unknown_key', 'disabled', 'over_cap', 'not_entitled',
                 'unknown_checkpoint', 'too_large', 'client_outdated', 'malformed', 'new',
                 'expired', 'evicted', 'idle_timeout', 'session_expired', 'server_restart',
                 'unknown_session', 'session_not_found'}


def error_response(error):
    code, reason = getattr(error, 'code', None), getattr(error, 'reason', None)
    delay = getattr(error, 'retry_after_s', None)
    return dict(ok=False, error_type=type(error).__name__,
                code=code if isinstance(code, str) and code in ERROR_CODES else None,
                reason=reason if isinstance(reason, str) and reason in ERROR_REASONS else None,
                retryable=getattr(error, 'retryable', False) is True,
                retry_after_s=delay if type(delay) in (float, int) and math.isfinite(delay) and delay >= 0 else None)


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
                response = error_response(error)
            print(json.dumps(response, default=lambda value: value.tolist(), allow_nan=False), flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
