"""SDK setup can overlap native Home; prediction cannot bypass Home feedback."""
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from remote_yam.controller import RunnerController
from remote_yam.latency_spans import journal_span
from remote_yam.session import MockSessionAPI
from test_dream_policy import DreamWorker, Worker, adapter, observation


def controller_with_policy(tmp_path, worker=Worker):
    policy = adapter(tmp_path, worker_pool=threading.BoundedSemaphore(1))
    policy.worker_factory = worker
    api = MockSessionAPI(auto_activate=False)
    controller = RunnerController(api, share_conversation=False)
    controller.join(policy, 'synthetic fixture')
    policy.start_preparation(lambda: controller._provider_cancelled(policy))
    return controller, policy, api


def event(controller, kind, payload, episode='episode'):
    controller._handle_event(dict(schema_version=1, session_id=controller._session_id,
                                 type=kind, episode_id=episode, payload=payload))


def test_lease_event_starts_sdk_while_home_is_pending_without_predicting(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class PreparingWorker(Worker):
        def __init__(self, *args):
            super().__init__(*args); self.hold = release
        def call(self, command, **kwargs):
            if command == 'configure':
                entered.set(); assert release.wait(2)
            return super().call(command, **kwargs)
    controller, policy, api = controller_with_policy(tmp_path, PreparingWorker)
    try:
        assert policy._preparation is None and policy._worker is None
        event(controller, 'snapshot', {'status':'queued'})
        assert policy._preparation is None
        # The real lifecycle payload does not contain lease_id.
        event(controller, 'lifecycle', {'state':'preparing', 'reason':'jetson_leased'})
        assert entered.wait(1)
        assert controller._status == 'preparing' and not api.action_log
        assert policy._collector is None
        release.set(); assert policy._ready.wait(1)
        assert not any(command=='predict' for command, _ in policy._worker.calls)
        assert controller._status == 'preparing' and not api.action_log
        timing = [e['details']['stage'] for e in controller._interactions.events if e['kind']=='policy_timing']
        assert {'lease_preparation','worker_acquisition','worker_start','worker_configure'} <= set(timing)
    finally:
        release.set(); policy.close_transport()


def test_leased_snapshot_prepares_sdk_and_stop_releases_the_single_slot(tmp_path):
    controller, policy, api = controller_with_policy(tmp_path)
    try:
        event(controller, 'snapshot', {'status':'preparing','episode_id':'episode','lease_id':'lease'})
        assert policy._ready.wait(1)
        worker = policy._worker
        assert worker is not None and not api.action_log
        controller.stop()
        assert worker.closed.wait(1)
        assert policy.worker_pool.acquire(blocking=False)
        policy.worker_pool.release()
    finally:
        policy.close_transport()


@pytest.mark.parametrize('homed', [False, True])
def test_ready_sdk_still_requires_confirmed_home_before_prediction(tmp_path, homed, monkeypatch):
    policy = adapter(tmp_path)
    policy.wait_ready(lambda: False)
    payload = dict(observation(), source='hardware', step_id=0, episode_id='episode', lease_id='lease',
                   settled=True, homed=homed, mode='API_ACTIVE', safety={'ok':True,'estop_engaged':False})
    policy.observation_source = lambda: dict(payload, observed_at=time.time())
    live = dict(status='running', episode_id='episode', lease_id='lease', latest_observation_step=0,
                active_trajectory=None)
    api = SimpleNamespace(supports_trajectories=True, get_session=lambda sid:live,
                          get_robot_observation=lambda rid:dict(payload, observed_at=time.time()))
    controller = RunnerController(api)
    controller._provider = policy; controller._status = 'running'
    controller._session_id = 'session'; controller._episode_id = 'episode'; controller._lease_id = 'lease'
    controller.update_monitor_observation(payload)
    dispatched = []
    def guarded_dispatch(builder, provider, prompt, state, *context):
        assert state['homed'] is True and state['settled'] is True
        dispatched.append(builder(prompt, state, context[-1]))
    controller._dispatch_trajectory = guarded_dispatch
    monkeypatch.setattr('remote_yam.controller.FEEDBACK_WAIT_S', .01)
    try:
        if homed:
            controller._observation({}, payload)
            assert dispatched and any(c=='predict' for c, _ in policy._worker.calls)
        else:
            with pytest.raises(RuntimeError, match='Hardware feedback blocked'):
                controller._observation({}, payload)
            assert not dispatched and not any(c=='predict' for c, _ in policy._worker.calls)
    finally:
        policy.close_transport()


def test_camera_boundaries_are_not_logged_at_each_background_tick(tmp_path):
    policy = adapter(tmp_path)
    events = []
    policy.interaction_sink = lambda kind, message, **details: events.append((kind, details))
    policy._prompt = 'synthetic fixture'
    ticks = [policy._capture_tick() for _ in range(3)]
    assert [tick['capture_timing']['capture_id'] for tick in ticks] == [1,2,3]
    assert sum(details.get('stage')=='camera_acquisition' for _, details in events) == 2
    assert all(tick['capture_timing']['camera_capture_s'] >= 0 for tick in ticks)
    assert 'synthetic fixture' not in json.dumps(events)
    assert 'frames' not in json.dumps(events)


def test_timing_sink_failure_cannot_interrupt_control():
    body = []
    def broken(*args, **kwargs): raise OSError('unavailable diagnostic sink')
    with journal_span(broken, 'synthetic_stage'):
        body.append('ran')
    assert body == ['ran']


def test_dream_does_not_use_astra_saved_home_prediction(tmp_path):
    controller, policy, api = controller_with_policy(tmp_path)
    api.supports_trajectories = True
    api.home_scene = lambda *args: pytest.fail('Dream must not request a saved Home scene')
    try:
        controller._poll_home_scene()
        assert controller._home_plan is None and policy._worker is None
    finally:
        policy.close_transport()


def test_worker_preserves_stage_start_when_stop_interrupts_configuration(tmp_path, monkeypatch):
    sdk = tmp_path/'sdk'; sdk.mkdir()
    (sdk/'dream.py').write_text('''
import time
__version__='1.0.0'
class DreamClient:
    def policy(self, config): time.sleep(30)
    def close(self): pass
''')
    monkeypatch.setenv('PYTHONPATH', str(sdk))
    worker = DreamWorker(sys.executable, tmp_path/'synthetic_credentials', tmp_path/'worker')
    errors = []
    def configure():
        try:
            worker.call('configure', checkpoint='dreamlabs/dream-1-beta')
        except RuntimeError as error:
            errors.append(type(error).__name__)
    thread = threading.Thread(target=configure); thread.start()
    trace = tmp_path/'worker/stage-timings.jsonl'
    try:
        deadline = time.monotonic()+5
        rows = []
        while time.monotonic()<deadline:
            if trace.exists():
                rows = [json.loads(line) for line in trace.read_text().splitlines()]
                if any(row['stage']=='sdk_configure' and row['state']=='started' for row in rows):
                    break
            time.sleep(.02)
        assert any(row['stage']=='sdk_configure' and row['state']=='started' for row in rows)
        assert not any(row['stage']=='sdk_configure' and row['state']=='completed' for row in rows)
        assert trace.stat().st_mode & 0o777 == 0o600
    finally:
        worker.close(); thread.join(2)
    assert worker.process.poll() is not None and not thread.is_alive() and errors
