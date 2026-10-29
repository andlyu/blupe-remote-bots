from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from remote_yam.controller_executor import (ControllerExecutorPolicy, DREAM_MODEL,
    ROBOHOUSE, execution_request, selected_executor)


@pytest.mark.parametrize('executor', [None])
def test_null_executor_makes_no_execution_request(executor):
    api = Mock()
    assert selected_executor(executor, provider='openai', model='anything', robot_id='any') is None
    assert execution_request(api, {}, executor) is None
    assert not api.mock_calls


@pytest.mark.parametrize('change', [dict(executor='unknown'), dict(executor=''),
    dict(executor=[]), dict(provider='dream_flash'), dict(model='other'), dict(robot_id='yam-1')])
def test_invalid_route_never_constructs_controller_policy(change):
    args = dict(executor='dream_one', provider='dream', model=DREAM_MODEL, robot_id=ROBOHOUSE)
    args.update(change)
    with pytest.raises(ValueError):
        selected_executor(**args)


def test_only_executor_envelope_is_sent_with_existing_lease_and_capability():
    api = Mock()
    api._capability.return_value = 'capability'
    context = dict(session_id='session', episode_id='episode', lease_id='lease')
    execution_request(api, context, 'dream_one', request_id='a'*32)
    api._request.assert_called_once_with('POST', '/v1/sessions/session/executions', dict(
        schema_version=1, executor='dream_one', operation='start', payload={},
        episode_id='episode', lease_id='lease', request_id='a'*32), bearer='capability')


def test_policy_polls_existing_execution_route_without_reading_images_or_submitting_actions(monkeypatch):
    calls = []
    def request(method, path, payload=None, **kwargs):
        calls.append((method, path, payload))
        if method == 'POST':
            return dict(request_id='a'*32, status='pending')
        return dict(status='completed', result=dict(state='completed'))
    api = SimpleNamespace(_request=request, _capability=lambda sid: 'cap')
    monkeypatch.setattr('remote_yam.controller_executor.time.sleep', lambda _: None)
    result = ControllerExecutorPolicy().run_session('task', {}, api,
        dict(session_id='s', episode_id='e', lease_id='l'), lambda: False)
    assert result == {'state': 'completed'}
    assert len(calls) == 2
    assert calls[0][2]['payload'] == {}


def test_policy_cancelled_before_start_has_no_http_side_effect():
    api = Mock()
    ControllerExecutorPolicy().run_session('task', {}, api, {}, lambda: True)
    assert not api.mock_calls


@pytest.mark.parametrize('http_error', [False, True])
def test_controller_duration_expiring_during_execution_poll_keeps_timeout_cause(monkeypatch, http_error):
    from remote_yam.controller import RunnerController
    from remote_yam.session import MockSessionAPI, SessionAPIError
    now = [1119.9]
    monkeypatch.setattr('remote_yam.controller.time.time', lambda: now[0])
    api = MockSessionAPI()
    api._capability = lambda sid: 'cap'
    def request(*args, **kwargs):
        now[0] = 1120.1
        if http_error:
            raise SessionAPIError('Session is not active', status=409)
        return {'status': 'failed'}
    api._request = Mock(side_effect=request)
    api.get_session = Mock(return_value={'status': 'running'})  # Terminal event is still queued.
    api.stop_session = Mock()
    controller = RunnerController(api, robot_id=ROBOHOUSE, share_conversation=False)
    controller._provider = ControllerExecutorPolicy()
    controller._session_id = 'duration-session'; controller._episode_id = 'episode'
    controller._lease_id = 'lease'; controller._status = 'running'
    controller._run_started_at = 1000; controller._run_duration_s = 120
    observation = dict(step_id=0, source='simulation', jetson_id=ROBOHOUSE,
        observed_at=now[0], left_joints_deg=[0.]*6, right_joints_deg=[0.]*6,
        left_gripper=.5, right_gripper=.5, settled=True, homed=True)
    controller._monitor_observation = observation
    controller._poll_home_scene = Mock(); controller._cancel_home_plan = Mock()
    controller.process_next_event = lambda _: controller._observation({}, observation)
    controller._run_loop(None)
    state = controller.status()
    assert state['status'] == 'timed_out'
    assert 'Controller Dream execution request failed' not in (state['error'] or '')
    api.stop_session.assert_called_once_with('duration-session', reason='policy_runtime_timeout')
    assert api._request.call_count == 1


def test_active_controller_execution_failure_is_not_retried_or_hidden():
    api = SimpleNamespace(_request=Mock(return_value={'status': 'failed'}),
                          _capability=lambda sid: 'cap')
    with pytest.raises(RuntimeError, match='Controller Dream execution request failed'):
        ControllerExecutorPolicy().run_session('task', {}, api,
            dict(session_id='s', episode_id='e', lease_id='l'), lambda: False)
    assert api._request.call_count == 1
