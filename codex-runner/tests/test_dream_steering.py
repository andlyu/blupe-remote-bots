"""Owner guidance crosses Dream's real adapter/SDK boundary without robot IO."""
import copy
import asyncio
import json
import shutil
import sys
import time
from unittest.mock import patch

import pytest

from remote_yam.steering import SteeringInbox
from test_dream_policy import adapter, observation, Cameras, Worker, DreamWorker


def predict_calls(provider):
    return [payload for command, payload in provider._worker.calls if command == 'predict']


def test_dream_opts_into_the_existing_owner_steering_path(tmp_path):
    provider = adapter(tmp_path)
    try:
        assert provider.supports_runtime_steering is True
        assert isinstance(provider.steering, SteeringInbox)
    finally:
        provider.close_transport()


def test_guidance_between_completed_chunks_reaches_next_prediction_and_persists(tmp_path):
    provider = adapter(tmp_path)
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append((kind, message, details))
    try:
        first = provider.build_trajectory('Put the orange block on the towel', observation(), 0)
        worker = provider._worker
        provider.trajectory_completed(observation(), len(first))
        completed_anchor = copy.deepcopy(provider._commanded)
        provider.steering.submit('Approach from the right', 'request_000000001')
        second = provider.build_trajectory('Put the orange block on the towel', observation(), len(first))
        provider.trajectory_completed(observation(), len(second))
        provider.build_trajectory('Put the orange block on the towel', observation(), len(first) + len(second))
        calls = predict_calls(provider)
        for call in calls[1:]:
            prompt = call['ticks'][-1]['observation']['prompt']
            assert 'Put the orange block on the towel' in prompt
            assert 'Approach from the right' in prompt
            assert prompt.count('Approach from the right') == 1
        assert calls[1]['commanded'] == completed_anchor
        assert provider._worker is worker
        assert not any(command == 'reset' for command, _ in worker.calls)
        assert len([event for event in events if event[0] == 'steering_included']) == 1
        assert provider.steering.snapshot()[0]['state'] == 'included'
    finally:
        provider.close_transport()


def test_guidance_during_inference_discards_old_action_and_requeries_same_step(tmp_path):
    provider = adapter(tmp_path)
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append((kind, message, details))
    try:
        provider.wait_ready(lambda: False)
        original = provider._worker.call
        def call(command, **kwargs):
            reply = original(command, **kwargs)
            if command == 'predict' and len(predict_calls(provider)) == 1:
                provider.steering.submit('Use the other arm', 'request_000000001')
                # Recognizable invalid old result proves it never reaches packet conversion.
                return {'ok': True, 'result': {'action': {'old_prediction': True}}}
            return reply
        provider._worker.call = call
        points = provider.build_trajectory('Place the block', observation(), 0)
        calls = predict_calls(provider)
        assert len(calls) == 2 and points
        assert [call['first_step_id'] for call in calls] == [0, 0]
        assert 'Use the other arm' not in calls[0]['ticks'][-1]['observation']['prompt']
        assert 'Use the other arm' in calls[1]['ticks'][-1]['observation']['prompt']
        assert calls[1]['ticks'][-1]['timestamp'] > calls[0]['ticks'][-1]['timestamp']
        assert calls[1]['commanded'] is not None  # The unused action cannot become a smoothing anchor.
        assert not any(command == 'reset' for command, _ in provider._worker.calls)
        assert any(kind == 'model_progress' and 'discarded' in message for kind, message, _ in events)
    finally:
        provider.close_transport()


def test_prompt_guidance_is_ordered_idempotent_and_keeps_original_goal():
    inbox = SteeringInbox(lambda *args, **kwargs: None)
    assert inbox.include_prompt('Original task') is None
    inbox.submit('Use the right arm', 'request_000000001')
    first = inbox.include_prompt('Original task')
    assert 'Original task' in first and 'Use the right arm' in first
    assert inbox.include_prompt('Original task') is None
    inbox.submit('Use the right arm', 'request_000000001')
    with patch('remote_yam.steering.time.monotonic', return_value=time.monotonic() + 2):
        inbox.submit('Lift before moving sideways', 'request_000000002')
    second = inbox.include_prompt('Original task')
    assert second.index('Use the right arm') < second.index('Lift before moving sideways')
    assert 'newer' in second
    assert all(row['state'] == 'included' for row in inbox.snapshot())


def test_cancelled_run_never_consumes_queued_guidance(tmp_path):
    provider = adapter(tmp_path)
    try:
        provider.steering.submit('Lift first', 'request_000000001')
        provider.cancelled = lambda: True
        with pytest.raises(RuntimeError, match='cancelled'):
            provider.build_trajectory('Original task', observation(), 0)
        assert provider._worker is None
        assert provider.steering.snapshot(active=False)[0]['state'] == 'not_delivered'
    finally:
        provider.close_transport()


def test_real_worker_passes_new_prompt_to_sdk_without_resetting_session(tmp_path, monkeypatch):
    sdk = tmp_path / 'controlled_sdk'
    sdk.mkdir()
    trace = tmp_path / 'sdk-prompts.jsonl'
    (sdk / 'dream.py').write_text('''
import json, os
__version__ = '1.0.0'
class DreamClient:
    last_timing = {'rtt_ms': 1}
    def __init__(self): self.session_id = None
    def policy(self, config): pass
    def reset_episode(self): raise AssertionError('Steering must not reset the SDK episode')
    def close(self): pass
    def set_observation(self, frames, observation, timestamp):
        self.observation = observation
    def get_action(self, commanded=None):
        with open(os.environ['TEST_PROMPT_TRACE'], 'a') as out:
            out.write(json.dumps(dict(prompt=self.observation['prompt'], session_id=self.session_id))+'\\n')
        self.session_id = 'same-fixture-session'
        grip = .8 if 'Approach from the right' in self.observation['prompt'] else .2
        return {key: [list(self.observation['state.'+side+'_arm'])+[grip] for _ in range(48)]
                for key, side in [('q_l_chunk','left'), ('q_r_chunk','right')]}
''')
    monkeypatch.setenv('PYTHONPATH', str(sdk))
    monkeypatch.setenv('TEST_PROMPT_TRACE', str(trace))
    provider = adapter(tmp_path / 'bridge')
    provider.python = sys.executable
    provider.worker_factory = DreamWorker
    try:
        first = provider.build_trajectory('Place the orange block', observation(), 0)
        provider.trajectory_completed(observation(), len(first))
        worker = provider._worker
        provider.steering.submit('Approach from the right', 'request_000000001')
        second = provider.build_trajectory('Place the orange block', observation(), len(first))
        assert first[-1]['right_gripper'] == .2 and second[-1]['right_gripper'] == .8
        assert provider._worker is worker
        rows = [json.loads(row) for row in trace.read_text().splitlines()]
        assert rows[0]['prompt'] == 'Place the orange block'
        assert 'Approach from the right' in rows[1]['prompt']
        assert [row['session_id'] for row in rows] == [None, 'same-fixture-session']
    finally:
        provider.close_transport()


def test_authenticated_steering_endpoint_enables_and_delivers_to_dream(tmp_path, monkeypatch):
    import playground
    import test_hosted
    from remote_yam.controller import RunnerController
    from remote_yam.session import MockSessionAPI
    credentials = tmp_path / 'credentials'
    credentials.write_text('synthetic only')
    api = MockSessionAPI(auto_activate=False)
    app = playground.HostedRunner(public_origin='https://robot.example', session_api='https://session.example',
        camera_origin='http://127.0.0.1:8089', api_factory=lambda: api,
        dream_credentials_file=str(credentials), dream_python='/inert/python', dream_worker_factory=Worker)
    harness = type('Harness', (), {'app': app})()
    # Keep queue processing inert; the real controller still owns the inbox and attempt.
    monkeypatch.setattr(RunnerController, 'join_and_run', RunnerController.join)
    def call(path, **kwargs):
        return asyncio.run(test_hosted.HostedTests.call(harness, path, **kwargs))
    try:
        _, session, headers = call('/api/session', method='POST')
        browser = dict(cookie=headers[b'set-cookie'].decode().split(';', 1)[0], csrf=session['csrf'])
        code, _, _ = call('/api/run', method='POST', payload=dict(provider='dream',
            model='dreamlabs/dream-1-beta', prompt='Place the orange block'), **browser)
        assert code == 200
        controller = next(iter(app.visitors.values())).controller
        with controller._lock:
            controller._status = 'running'
        provider = controller._provider
        provider.camera_source, provider.observation_source = Cameras(), observation
        state = controller.status()
        assert state['steering']['available'] is True
        code, _, _ = call('/api/steer', method='POST', payload=dict(attempt_id=state['attempt_id'],
            request_id='request_000000001', text='Approach from the right'), **browser)
        assert code == 200
        assert controller.status()['steering']['messages'][0]['state'] == 'queued'
        provider.build_trajectory('Place the orange block', observation(), 0)
        assert 'Approach from the right' in predict_calls(provider)[0]['ticks'][-1]['observation']['prompt']
        assert controller.status()['steering']['messages'][0]['state'] == 'included'
        assert not api.action_log and not api.trajectory_log
    finally:
        for visitor in app.visitors.values():
            visitor.controller.stop()
        shutil.rmtree(app.root, ignore_errors=True)
