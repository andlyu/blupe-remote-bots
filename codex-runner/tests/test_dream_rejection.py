"""Synthetic provider refusals through the real public error/history paths."""
import sqlite3

import pytest

from remote_yam.past_runs import RunNames
from remote_yam.run_errors import public_run_error


MESSAGE = 'Dream1 rejected this prompt.'


def test_real_adapter_refusal_is_displayed_without_retry_or_action(tmp_path):
    from test_dream_policy import adapter, SessionWorker, observation

    provider = adapter(tmp_path)
    provider.worker_factory = SessionWorker
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append(
        dict(kind=kind, message=message, details=details))
    try:
        provider.wait_ready(lambda: False)
        provider._worker.responses = [dict(ok=False, error_type='DreamBadRequest',
            code='DA-4000', reason='malformed', phase='predict', retryable=False)]
        with pytest.raises(RuntimeError) as failed:
            provider.build_trajectory('put orange block on towel', observation(), 0)
        state = dict(status='failed', error='RuntimeError: ' + str(failed.value),
                     interactions=dict(events=events))
        assert public_run_error(state) == MESSAGE
        assert len([c for c, _ in provider._worker.calls if c == 'predict']) == 1
        assert provider._pending_commanded is None
    finally:
        provider.close_transport()


def native_failure(**changes):
    failure = dict(error_type='DreamBadRequest', code='DA-4000', phase='predict',
                   reason='malformed', message='private provider response')
    failure.update(changes)
    return dict(status='failed', error='Controller Dream execution failed',
                safety_error=dict(code='controller_executor_failed',
                    details=dict(provider=failure)))


@pytest.mark.parametrize('state', [
    dict(status='failed', error='RuntimeError: Dream request failed (DA-4000; DreamBadRequest; malformed)'),
    dict(status='failed', error='Dream request failed (DA-4000; DreamBadRequest)'),
    native_failure(),
    dict(status='failed', error='Dream request failed', interactions=dict(events=[
        dict(kind='model_failure', details=dict(error_type='DreamBadRequest', code='DA-4000'))])),
    dict(status='stopped', error=MESSAGE),
])
def test_rejection_has_one_plain_public_message(state):
    assert public_run_error(state) == MESSAGE


@pytest.mark.parametrize('failure', [
    dict(error_type='DreamProtocolError', code=None),
    dict(error_type='DreamTimeout', code=None),
    dict(error_type='DreamAuthError', code='DA-1000'),
    dict(error_type='DreamServerError', code='DA-2000', reason='rate_limited'),
    dict(error_type='DreamServerError', code='DA-5000'),
    dict(error_type='DreamServerError', code='DA-6000', reason='cannot_scale'),
])
def test_other_failures_do_not_blame_the_prompt(failure):
    assert public_run_error(native_failure(**failure)) != MESSAGE


def test_hardware_failure_and_deadline_keep_priority():
    state = native_failure()
    state['safety_error']['details']['native_code'] = 'joint_velocity_limit'
    assert public_run_error(state) != MESSAGE
    state = native_failure()
    state['status'] = 'timed_out'
    assert public_run_error(state) == 'Run reached time limit'


def test_old_rejection_event_does_not_mark_a_healthy_run_rejected():
    state = native_failure()
    state.update(status='running', error=None, safety_error=None)
    state['interactions'] = dict(events=[dict(kind='model_failure',
        details=dict(error_type='DreamBadRequest', code='DA-4000'))])
    assert public_run_error(state) is None


def test_native_rejection_is_saved_with_the_same_public_result(tmp_path):
    names = RunNames(tmp_path / 'runs.sqlite')
    names.remember_result('ep_rejected', native_failure())
    with sqlite3.connect(names.path) as db:
        assert db.execute('SELECT reason FROM run_results').fetchone() == (MESSAGE,)
        assert db.execute('SELECT errors FROM run_details').fetchone() == (MESSAGE,)
