from remote_yam.run_errors import public_run_error

import pytest


def test_velocity_rejection_shows_specific_reason_without_private_exception_text():
    state = {'status': 'stopped', 'error':
        'RuntimeError: joint_velocity_limit: Trajectory rejected before motion by Safety Guardrails'}
    assert public_run_error(state) == 'Robot rejected the action packet before motion: joint velocity limit exceeded.'
    state['error'] += ' PRIVATE PAYLOAD'
    assert public_run_error(state) == 'The run encountered a model or runner error.'


@pytest.mark.parametrize('prefix', ['', 'RuntimeError: '])
def test_adjacent_delta_rejection_includes_packet_entry_boundary(prefix):
    state = {'status': 'stopped', 'error': prefix +
        'adjacent_delta_limit: Trajectory rejected before motion by Safety Guardrails'}
    assert public_run_error(state) == (
        'Robot rejected the action packet before motion: joint step limit exceeded '
        'between the current position and the first waypoint, or between waypoints.')


@pytest.mark.parametrize('error', [
    'RuntimeError: adjacent_delta_limit: Trajectory rejected before motion by Safety Guardrails PRIVATE PAYLOAD',
    'RuntimeError: unknown_limit: Trajectory rejected before motion by Safety Guardrails',
    'PRIVATE PAYLOAD adjacent_delta_limit: Trajectory rejected before motion by Safety Guardrails',
])
def test_unknown_or_unbounded_gateway_error_stays_private(error):
    assert public_run_error({'status': 'stopped', 'error': error}) == 'The run encountered a model or runner error.'
