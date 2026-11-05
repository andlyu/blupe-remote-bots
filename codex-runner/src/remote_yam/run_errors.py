"""Public run errors with the recorded cause and credential redaction."""
import re

from remote_yam.past_runs import public_robot_error, run_timed_out, public_runner_diagnostic
from remote_yam.public_task_progress import public_text


def public_error_detail(state):
    """Retain unknown exception messages instead of hiding their cause."""
    safety = state.get('safety_error') or {}
    candidates = [state.get('error'), safety.get('message'), safety.get('code')]
    candidates.extend(event.get('message') for event in reversed(
        (state.get('interactions') or {}).get('events', [])) if event.get('kind') == 'error')
    generic = {'The run encountered a model or runner error.', 'Runner or model error'}
    value = next((item for item in candidates if isinstance(item, str) and item.strip()
                  and item.strip() not in generic), None)
    if value is None:
        return 'Run failed without a recorded error detail.'
    text = re.sub(r'''https?://[^\s<>"']+''', '[URL redacted]', value, flags=re.I)
    text = public_text(text)
    text = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[^\s,;]+', '[credential redacted]', text)
    text = re.sub(
        r'''(?i)(\b(?:api[-_]?key|access[-_]?token|refresh[-_]?token|token|password|secret|authorization|cookie)\b["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}\]]+)''',
        r'\1[redacted]', text)
    text = re.sub(r'\b(?:AIza[\w-]{20,}|AKIA[A-Z0-9]{16}|github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+)',
                  '[redacted]', text)
    text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
    return ' '.join(text.split())[:2000]


def public_run_error(state):
    specific = public_robot_error(state)
    if specific:
        return specific
    if run_timed_out(state):
        return 'Run reached time limit'
    diagnostic = public_runner_diagnostic(state)
    if diagnostic:
        return diagnostic
    error = state.get('error')
    safety = state.get('safety_error') or {}
    observation = (safety.get('details') or {}).get('observation') or {}
    if observation.get('state') == 'failed':
        field = observation.get('field')
        if not isinstance(field, str):
            field = None
        if field in {'camera_left', 'camera_top', 'camera_right', 'camera_capture', 'camera_roles'}:
            view = field[7:] + ' camera' if field in {'camera_left', 'camera_top', 'camera_right'} else 'camera'
            status = observation.get('http_status')
            detail = f' (HTTP {status})' if type(status) is int and 400 <= status <= 599 else ''
            return f'Run stopped: {view} frames remained unavailable{detail}.'
        if field in {'observation', 'observation_source', 'observed_at', 'jetson_id',
                     'left_joints_deg', 'right_joints_deg', 'left_gripper', 'right_gripper'}:
            return 'Run stopped: fresh robot feedback remained unavailable.'
    if error or safety:
        text = str(error or safety.get('code') or '').lower()
        if 'claude code needs sign-in' in text:
            return 'Claude subscription sign-in expired or was rejected. Reconnect Claude in the local runner.'
        if 'codex needs chatgpt sign-in' in text:
            return 'ChatGPT subscription sign-in expired or was rejected. Reconnect Codex in the local runner.'
        if 'runtime limit' in text or 'session_timeout' in text or 'policy_runtime_timeout' in text:
            return 'Run reached time limit'
        if '401' in text or 'authentication' in text or 'invalid_api_key' in text:
            return 'Model provider rejected the API credentials.'
        if '429' in text or 'rate_limit' in text or 'quota' in text:
            return 'Model provider rate limit or quota exceeded.'
        if 'camera' in text:
            return 'Run could not obtain a camera frame.'
        if safety.get('category') == 'hardware_safety':
            return 'Robot safety check failed; motion was stopped.'
        if 'timeout' in text or 'timed out' in text:
            return 'Run request timed out.'
        if 'connection' in text or 'urlerror' in text or state.get('status') == 'disconnected':
            return 'Run lost its connection to the model provider or robot server.'
        return public_error_detail(state)
    if state.get('status') in {'preparing', 'running'}:
        if state.get('server_contact_issue'):
            return 'Connection issue with the model provider or robot server; retrying.'
        retry = ((state.get('provider') or {}).get('vision') or {}).get('retry') or {}
        if retry.get('state') == 'retrying':
            return 'Camera frame unavailable; retrying.'
    return None
