"""Fixed public failure categories shared by local and configured web runners.

Raw exceptions and executable receipts remain private. Neither a peer's message
nor an unknown code is ever accepted as public wording.
"""
MESSAGES = {
    'queue_api_owner': 'Robot initialization was blocked by queue/API ownership.',
    'runner_unavailable': 'Configured runner is unavailable; no reset was started.',
    'runner_version': 'Configured runner policy version differs from the hosted version.',
    'start_unconfirmed': 'Reset start was not confirmed; it was not retried.',
    'receipt_missing': 'Configured program exited without a terminal receipt; its outcome is unconfirmed.',
    'receipt_mismatch': 'Configured program returned a receipt for a different request; its outcome is unconfirmed.',
    'goals_not_reached': 'Reset did not reach its goals; terminal evidence is retained by the configured runner.',
    'request_has_evidence': 'This request already has execution evidence; it was not retried.',
    'source_changed': 'Configured policy source changed; execution was not started.',
    'joint_velocity_limit': 'Robot rejected the action packet before motion: joint velocity limit exceeded.',
    'adjacent_delta_limit': ('Robot rejected the action packet before motion: joint step limit exceeded '
                             'between the current position and the first waypoint, or between waypoints.'),
}
SIGNATURES = {
    'Queue/API owner blocks initialization': 'queue_api_owner',
    'Configured runner is unavailable; no reset was started': 'runner_unavailable',
    'Configured runner policy version differs': 'runner_version',
    'Reset start was not confirmed; it was not retried': 'start_unconfirmed',
    'Executable exited without a terminal receipt; inspect command.log': 'receipt_missing',
    'Executable receipt does not match this request': 'receipt_mismatch',
    'Reset goals were not reached; inspect terminal receipt': 'goals_not_reached',
    'Reset did not reach its goals; terminal evidence is retained by the configured runner': 'goals_not_reached',
    'This executable request already has evidence; do not retry it': 'request_has_evidence',
    'joint_velocity_limit: Trajectory rejected before motion by Safety Guardrails': 'joint_velocity_limit',
    'adjacent_delta_limit: Trajectory rejected before motion by Safety Guardrails': 'adjacent_delta_limit',
    **{message: code for code, message in MESSAGES.items()},
}


def public_failure(code):
    if isinstance(code, str) and code in MESSAGES:
        return dict(code=code, message=MESSAGES[code])
    return None


def failure_from_error(error):
    if not isinstance(error, str):
        return None
    if error.startswith(('RuntimeError: ', 'ValueError: ')):
        error = error.split(': ', 1)[1]
    code = SIGNATURES.get(error)
    # The configured source path is deliberately never part of public wording.
    if error.startswith('Configured policy source changed: '):
        code = 'source_changed'
    return public_failure(code)


def failure_from_state(state):
    failure = failure_from_error(state.get('error'))
    if failure:
        return failure
    execution = (state.get('provider') or {}).get('managed_execution') or {}
    if execution.get('phase') == 'failed':
        supplied = execution.get('failure')
        if isinstance(supplied, dict):
            return public_failure(supplied.get('code'))
    return None
