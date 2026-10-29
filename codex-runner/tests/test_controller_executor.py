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
