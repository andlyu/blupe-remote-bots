"""JSON-lines bridge to an isolated Dream SDK environment. No robot transport."""
import json
import math
import os
from pathlib import Path
import re
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


def error_response(error, *, phase=None, timing=None):
    code, reason = getattr(error, 'code', None), getattr(error, 'reason', None)
    delay = getattr(error, 'retry_after_s', None)
    response = dict(ok=False, error_type=type(error).__name__,
                code=code if isinstance(code, str) and code in ERROR_CODES else None,
                reason=reason if isinstance(reason, str) and reason in ERROR_REASONS else None,
                retryable=getattr(error, 'retryable', False) is True,
                retry_after_s=delay if type(delay) in (float, int) and math.isfinite(delay) and delay >= 0 else None)
    if phase in {'configure', 'reset', 'predict', 'observation'}:
        response['phase'] = phase
    if type(error).__name__ == 'DreamProtocolError':
        # SDK 1.0.0 embeds the endpoint in its message. Classify known static
        # branches locally; never forward that message or an arbitrary cause.
        message = str(error)
        status = re.search(r'is not JSON \(HTTP ([1-5][0-9]{2})\);', message)
        cause = type(error.__cause__).__name__ if error.__cause__ else None
        causes = {'JSONDecodeError', 'UnicodeDecodeError', 'BrokenPipeError',
                  'ConnectionResetError', 'RemoteDisconnected', 'ConnectionRefusedError',
                  'gaierror', 'SSLError', 'OSError', 'HTTPException', 'IncompleteRead',
                  'BadStatusLine'}
        category = ('non_json_reply' if status else
                    'missing_status_envelope' if message.startswith('inference reply carries no status envelope;') else
                    'connection_failure' if cause in causes - {'JSONDecodeError', 'UnicodeDecodeError'} else
                    'other_protocol_error')
        response.update(protocol_category=category,
                        http_status=int(status.group(1)) if status else None,
                        cause_type=cause if cause in causes else None)
    if isinstance(timing, dict):
        safe = {key: value for key, value in timing.items()
                if key in {'rtt_ms', 'request_bytes', 'response_bytes', 'serve_infer_ms', 'gateway_ms', 'network_ms'}
                and type(value) in (int, float) and math.isfinite(value) and value >= 0}
        if safe:
            response['timing'] = safe
    return response


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
            phase = None
            request_started = False
            try:
                kind = command['command']
                phase = kind
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
                    phase = 'observation'
                    for tick in command['ticks']:
                        if last_timestamp is not None and tick['timestamp'] <= last_timestamp:
                            continue
                        observation = {key: np.asarray(value, dtype=np.float32) if key.startswith('state.') else value
                                       for key, value in tick['observation'].items()}
                        client.set_observation(tick['frames'], observation, timestamp=tick['timestamp'])
                        last_timestamp = tick['timestamp']
                    phase = 'predict'
                    request_started = True
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
                response = error_response(error, phase=phase,
                                          timing=client.last_timing if request_started else None)
            print(json.dumps(response, default=lambda value: value.tolist(), allow_nan=False), flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
