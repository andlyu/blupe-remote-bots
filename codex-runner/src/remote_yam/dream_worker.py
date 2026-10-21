"""JSON-lines bridge to an isolated Dream SDK environment. No robot transport."""
import json
import http.client
import ssl
from contextlib import contextmanager
import math
import os
from pathlib import Path
import re
import signal
import sys

os.environ['DREAM_LOG'] = 'off'
os.environ.setdefault('LOGURU_LEVEL', 'WARNING')
os.environ.setdefault('JAX_COMPILATION_CACHE_DIR', str(Path(os.environ['DREAM_WORK_DIR']) / 'jax'))
if os.environ.get('YAM_DREAM_BLOCKWISE_IK', '0') == '1':
    # JAX's supported precision switch is process-wide, before SDK/JAX import.
    # It also keeps SDK-created values consistent with the float64 Gram/solve.
    os.environ['JAX_ENABLE_X64'] = '1'

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
        # Preserve bounded standard-library causes, including TLS/HTTP
        # subclasses. Exact-name-only matching hid SSL EOF as 'other'.
        cause = error.__cause__ or error.__context__
        names = {'JSONDecodeError', 'UnicodeDecodeError', 'BrokenPipeError',
                 'ConnectionResetError', 'RemoteDisconnected', 'ConnectionRefusedError',
                 'ConnectionAbortedError', 'TimeoutError', 'gaierror', 'herror',
                 'SSLError', 'SSLEOFError', 'SSLZeroReturnError', 'SSLWantReadError',
                 'SSLWantWriteError', 'SSLSyscallError', 'SSLCertVerificationError',
                 'OSError', 'HTTPException', 'IncompleteRead', 'BadStatusLine',
                 'CannotSendRequest', 'CannotSendHeader', 'ResponseNotReady',
                 'LineTooLong', 'NotConnected', 'UnknownProtocol', 'UnknownTransferEncoding'}
        family = ('tls' if isinstance(cause, ssl.SSLError) else
                  'http' if isinstance(cause, http.client.HTTPException) else
                  'network' if isinstance(cause, OSError) else
                  'json' if isinstance(cause, (json.JSONDecodeError, UnicodeDecodeError)) else None)
        name = type(cause).__name__ if cause is not None else None
        safe_name = name if name in names else {'tls':'SSLError', 'http':'HTTPException',
                                               'network':'OSError', 'json':'JSONDecodeError'}.get(family)
        category = ('non_json_reply' if status else
                    'missing_status_envelope' if message.startswith('inference reply carries no status envelope;') else
                    'connection_failure' if family in {'tls', 'http', 'network'} or
                        safe_name in names - {'JSONDecodeError', 'UnicodeDecodeError'} else
                    'other_protocol_error')
        trace, transport_stage = protocol_trace(error)
        if category == 'non_json_reply':
            transport_stage = 'response_decode'
        elif category == 'missing_status_envelope':
            transport_stage = 'response_envelope'
        number = getattr(cause, 'errno', None)
        reason = getattr(cause, 'reason', None)
        response.update(protocol_category=category,
                        http_status=int(status.group(1)) if status else None,
                        cause_type=safe_name, cause_family=family,
                        cause_errno=number if type(number) is int and abs(number) <= 65535 else None,
                        cause_reason=reason if isinstance(reason, str) and reason in {'UNEXPECTED_EOF_WHILE_READING',
                            'PROTOCOL_IS_SHUTDOWN', 'TLSV1_ALERT_INTERNAL_ERROR',
                            'SSLV3_ALERT_BAD_RECORD_MAC', 'CERTIFICATE_VERIFY_FAILED',
                            'WRONG_VERSION_NUMBER'} else None,
                        transport_stage=transport_stage, protocol_trace=trace,
                        http_connection_policy='fresh_per_exchange')
    if isinstance(timing, dict):
        safe = {key: value for key, value in timing.items()
                if key in {'rtt_ms', 'request_bytes', 'response_bytes', 'serve_infer_ms', 'gateway_ms', 'network_ms'}
                and type(value) in (int, float) and math.isfinite(value) and value >= 0}
        if safe:
            response['timing'] = safe
    return response


def protocol_trace(error):
    """Static module/function/line only; never filenames, text or frame locals."""
    allowed = {'dream.transport': {'request', '_exchange', 'decode'},
               'dream.client': {'get_action', '_post'}, 'dream.facade': {'get_action'},
               'http.client': {'request', '_send_request', 'endheaders', '_send_output',
                   'send', 'getresponse', 'begin', '_read_status', 'read', 'readinto',
                   '_safe_read', '_read_chunked', '_get_chunk_left', '_read_next_chunk_size'},
               'ssl': {'sendall', 'send', 'write', 'read', 'recv', 'recv_into'},
               'socket': {'readinto', 'create_connection'}}
    result, stage, seen = [], None, set()
    for _ in range(3):
        if error is None or id(error) in seen:
            break
        seen.add(id(error))
        tb = error.__traceback__
        while tb is not None:
            frame = tb.tb_frame
            module, function = frame.f_globals.get('__name__'), frame.f_code.co_name
            if module in allowed and function in allowed[module]:
                row = dict(module=module, function=function, line=tb.tb_lineno)
                if row not in result:
                    result.append(row)
                if module == 'http.client':
                    if function in {'request', '_send_request', 'endheaders', '_send_output', 'send'}:
                        stage = 'request_send'
                    elif function in {'getresponse', 'begin', '_read_status'}:
                        stage = 'response_headers'
                    elif function in {'read', 'readinto', '_safe_read', '_read_chunked',
                                      '_get_chunk_left', '_read_next_chunk_size'}:
                        stage = 'response_body'
            tb = tb.tb_next
        error = error.__cause__ or error.__context__
    return result[-8:], stage


def close_http_connection(client):
    # Pinned SDK1.0.0 _drop closes HTTP/TLS only; it retains PolicyClient's
    # model-session ID, smoother, observation window and compiled IK. A reused
    # Linux/OpenSSL3.0 socket can raise SSLEOFError during a write, which the
    # SDK's narrow stale-connection retry does not handle. Avoid reuse rather
    # than retrying an ambiguously processed inference. See refs/python/HTTP-TLS.
    transport = getattr(getattr(client, '_policy', None), '_transport', None)
    if transport is not None:
        transport._drop()


def reset_episode(client):
    close_http_connection(client)
    try:
        client.reset_episode()
    finally:
        close_http_connection(client)


def main():
    try:
        from .latency_spans import timed_span, journal_span
        from .dream_sdk_trace import DreamSDKTrace
    except ImportError:  # The isolated worker is launched by its script path.
        from latency_spans import timed_span, journal_span
        from dream_sdk_trace import DreamSDKTrace

    sdk_trace = DreamSDKTrace(os.environ['DREAM_WORK_DIR'])

    def stage_event(kind, message, **details):
        # Persist boundaries even when Stop interrupts configuration before a
        # reply. Keep stdout strictly one JSON response per worker command.
        path = Path(os.environ['DREAM_WORK_DIR'])/'stage-timings.jsonl'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps(details, allow_nan=False)+'\n')

    @contextmanager
    def stage(spans, name):
        with journal_span(stage_event, name):
            with timed_span(spans, name):
                yield

    startup_spans = []
    try:
        with stage(startup_spans, 'sdk_import'):
            import dream
            import numpy as np
        with stage(startup_spans, 'sdk_client_init'):
            client = dream.DreamClient()
    except Exception as error:
        print(json.dumps({**error_response(error, phase='configure'),
                          'stage_timings': startup_spans}), flush=True)
        return
    last_timestamp = None
    clients = {}
    prepared = False
    linear_algebra = 'dense'
    phase = None
    request_started = False

    def all_clients():
        return list({id(c): c for c in [client, *clients.values()] if c is not None}.values())

    def close(*_):
        for current in all_clients():
            current.close()
        raise SystemExit(0)

    def configure(client, command, spans):
        nonlocal linear_algebra
        if dream.__version__ != '1.0.0':
            raise ValueError('Unsupported Dream SDK version')
        if os.environ.get('YAM_DREAM_BLOCKWISE_IK', '0') == '1':
            try:
                from .dream_ik_blockwise import install_blockwise_gram
            except ImportError:
                from dream_ik_blockwise import install_blockwise_gram
            with stage(spans, 'ik_linear_algebra_install'):
                linear_algebra = install_blockwise_gram()
        checkpoint = command['checkpoint']
        if checkpoint not in ('dreamlabs/dream-1-beta', 'dreamlabs/dream-1-beta-flash'):
            raise ValueError('Unknown checkpoint')
        parts = {'right_arm': [0, 6], 'right_gripper': [6, 7],
                 'left_arm': [7, 13], 'left_gripper': [13, 14]}
        with stage(spans, 'sdk_configure'):
            client.policy(dict(checkpoint=checkpoint, robot='yam', strict=True,
                timeout_ms=15000, action_hz=20, ik={'arm': 'yam', 'head': 'eef', 'solve': 'traj'},
                embodiment={'state': parts, 'action': dict(parts),
                    'video': {role: 'observation.images.' + role
                              for role in ('overhead', 'wrist_l', 'wrist_r')}},
                _record=False))
        sdk_trace.install(client)

    def handle(command, spans):
        # Request payloads/arrays/actions live only in this call's frame, not in
        # the resident command loop after a release/reset. SDK windows are
        # cleared by its documented reset_episode() boundary (SDK 1.0.0).
        nonlocal client, last_timestamp, prepared, phase, request_started
        kind = command['command']
        phase = {'prime': 'configure', 'release': 'reset'}.get(kind, kind)
        if kind == 'prime':
            if prepared or clients:
                raise ValueError('Dream worker is already prepared')
            checkpoints = command['checkpoints']
            if (not checkpoints or len(set(checkpoints)) != len(checkpoints)
                    or any(c not in ('dreamlabs/dream-1-beta', 'dreamlabs/dream-1-beta-flash') for c in checkpoints)):
                raise ValueError('Unknown prepared checkpoint')
            variants = {}
            for checkpoint in checkpoints:
                current = client if not clients else dream.DreamClient()
                clients[checkpoint] = current
                configure(current, {'checkpoint': checkpoint}, spans)
                # SDK 1.0.0 compiles trajectory IK on a background thread. Read
                # its pinned readiness event; never advertise a partially
                # prepared solver. No observations or get_action are involved.
                with stage(spans, 'sdk_full_preparation'):
                    if not current._policy._ik.traj_ready.wait(120):
                        raise RuntimeError('Dream trajectory preparation failed')
                    try:
                        from .dream_ik_preparation import prepare_trajectory_variants
                    except ImportError:
                        from dream_ik_preparation import prepare_trajectory_variants
                    variants[checkpoint] = prepare_trajectory_variants(current._policy._ik)
            prepared = True
            client = None
            return {'sdk_version': dream.__version__, 'fully_ready': True,
                    'checkpoints': checkpoints, 'trajectory_variants': variants,
                    'ik_linear_algebra': linear_algebra}
        if kind == 'configure':
            checkpoint = command['checkpoint']
            if prepared:
                if checkpoint not in clients:
                    raise ValueError('Checkpoint was not prepared')
                if client is not None:
                    reset_episode(client)
                client = clients[checkpoint]
                with stage(spans, 'sdk_reset'):
                    reset_episode(client)
            else:
                configure(client, command, spans)
            last_timestamp = None
            return {'sdk_version': dream.__version__, 'prepared_reused': prepared,
                    'ik_linear_algebra': linear_algebra}
        if kind == 'release':
            with stage(spans, 'sdk_reset'):
                for current in all_clients():
                    reset_episode(current)
            if prepared:
                client = None
            last_timestamp = None
            return {}
        if client is None:
            raise RuntimeError('Dream visitor is not configured')
        if kind == 'reset':
            with stage(spans, 'sdk_reset'):
                reset_episode(client)
            last_timestamp = None
            return {}
        if kind == 'predict':
            phase = 'observation'
            with stage(spans, 'sdk_observation_update'):
                for tick in command['ticks']:
                    if last_timestamp is not None and tick['timestamp'] <= last_timestamp:
                        continue
                    observation = {key: np.asarray(value, dtype=np.float32) if key.startswith('state.') else value
                                   for key, value in tick['observation'].items()}
                    client.set_observation(tick['frames'], observation, timestamp=tick['timestamp'])
                    last_timestamp = tick['timestamp']
            phase = 'predict'
            request_started = True
            with stage(spans, 'sdk_get_action'):
                close_http_connection(client)
                try:
                    with sdk_trace.prediction(command.get('first_step_id')):
                        action = client.get_action(commanded=command.get('commanded'))
                finally:
                    close_http_connection(client)
            return {'action': action, 'timing': client.last_timing}
        raise ValueError('Unknown worker command')

    signal.signal(signal.SIGTERM, close)
    try:
        for line in sys.stdin:
            command = json.loads(line)
            if command.get('command') == 'close':
                return
            phase = None
            request_started = False
            spans = []
            try:
                result = handle(command, spans)
                response = {'ok': True, 'result': result}
            except Exception as error:
                response = error_response(error, phase=phase,
                                          timing=client.last_timing if request_started else None)
            response['stage_timings'] = startup_spans + spans
            startup_spans = []
            print(json.dumps(response, default=lambda value: value.tolist(), allow_nan=False), flush=True)
            # A reset/release replaces the command line too. Keep no previous
            # frame payload or action in these outer-loop references.
            del command, response
    finally:
        for current in all_clients():
            current.close()
        sdk_trace.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error_type': type(error).__name__}), flush=True)
        raise SystemExit(1)
