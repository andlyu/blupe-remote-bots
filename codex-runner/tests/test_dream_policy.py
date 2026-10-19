import base64
import io
import math
import threading
import time
import sys

from PIL import Image
import pytest

from remote_yam.cameras import CameraFrame
from remote_yam.dream_policy import DreamAdapter, DreamWorker, DreamObservationError, action_waypoints, motion_limited_waypoints, state_input


def observation():
    return dict(jetson_id='yam-1', observed_at=time.time(), left_joints_deg=[10] * 6,
                right_joints_deg=[20] * 6, left_gripper=.3, right_gripper=.7)


def action():
    return {'q_l_chunk': [[i / 1000] * 6 + [.2] for i in range(48)],
            'q_r_chunk': [[-i / 1000] * 6 + [.8] for i in range(48)]}


class Cameras:
    def capture_for_policy(self, observation, **kwargs):
        image = io.BytesIO()
        Image.new('RGB', (640, 360)).save(image, format='JPEG')
        return [CameraFrame(name, image.getvalue(), time.time()) for name in ('right', 'top', 'left')]


class Worker:
    def __init__(self, *args):
        self.calls = []
        self.closed = threading.Event()
        self.hold = None

    def call(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command == 'predict':
            if self.hold:
                self.hold.wait(2)
            return {'ok': True, 'result': {'action': action(), 'timing': {'rtt_ms': 600}}}
        return {'ok': True, 'result': {}}

    def close(self):
        self.closed.set()
        if self.hold:
            self.hold.set()


def adapter(tmp_path, **kwargs):
    return DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta', credentials='private-file',
        python='isolated-python', directory=tmp_path, camera_source=Cameras(),
        observation_source=observation, robot_id='yam-1', worker_factory=Worker, **kwargs)


def test_units_arm_order_endpoint_sampling_and_duration():
    state = state_input(observation(), 'move')
    assert state['state.left_arm'] == pytest.approx([math.radians(10)] * 6)
    assert state['state.right_gripper'] == [.7]
    points = action_waypoints(action(), 20)
    assert len(points) == 24 and points[-1]['step_id'] == 43
    assert points[0]['left_joints_deg'] == pytest.approx([math.degrees(.001)] * 6)
    assert points[-1]['right_joints_deg'] == pytest.approx([math.degrees(-.047)] * 6)
    assert points[-1]['left_gripper'] == .2 and points[-1]['right_gripper'] == .8
    assert len(points) / 10 == 48 / 20


@pytest.mark.parametrize('mutation', ['nan', 'grip', 'width', 'odd', 'mismatch', 'budget'])
def test_malformed_predictions_never_become_packets(mutation):
    result = action()
    first = 0
    if mutation == 'nan': result['q_r_chunk'][3][0] = float('nan')
    if mutation == 'grip': result['q_l_chunk'][4][6] = float('inf')
    if mutation == 'width': result['q_l_chunk'][0].pop()
    if mutation == 'odd': result['q_l_chunk'].pop(); result['q_r_chunk'].pop()
    if mutation == 'mismatch': result['q_l_chunk'] = result['q_l_chunk'][:46]
    if mutation == 'budget': first = 2990
    with pytest.raises(ValueError): action_waypoints(result, first)


def test_smoothed_gripper_endpoint_overshoot_matches_official_robot_adapter():
    result = action()
    # Real SDK 1.0.0 replay returned this slightly above-open value.
    result['q_l_chunk'][1][6] = 1.000013658216783
    result['q_r_chunk'][1][6] = -.00001
    points = action_waypoints(result, 0)
    assert points[0]['left_gripper'] == 1.
    assert points[0]['right_gripper'] == 0.
    assert points[0]['left_joints_deg'] == pytest.approx([math.degrees(.001)] * 6)
    assert result['q_l_chunk'][1][6] == 1.000013658216783


def test_motion_cap_slows_large_moves_preserving_paired_path_endpoints_and_ids():
    baseline = dict(observation(), left_joints_deg=[0.]*6, right_joints_deg=[0.]*6,
                    left_gripper=.5, right_gripper=.5)
    targets = [dict(step_id=31+i, left_joints_deg=[x, x/5, 0, 0, 0, 0],
        right_joints_deg=[-x/2, 0, 0, 0, 0, 0], left_gripper=.5, right_gripper=.5)
        for i,x in enumerate((39.,58.40116532478128))]
    points = motion_limited_waypoints(targets, baseline, 9.)
    assert len(points) == 8
    assert [p['step_id'] for p in points] == list(range(31,39))
    assert points[4]['left_joints_deg'] == targets[0]['left_joints_deg']
    assert points[-1]['left_joints_deg'] == targets[-1]['left_joints_deg']
    previous=baseline
    for point in points:
        assert point['right_joints_deg'][0] == pytest.approx(-point['left_joints_deg'][0]/2)
        for side in ('left','right'):
            assert max(abs(a-b) for a,b in zip(point[side+'_joints_deg'], previous[side+'_joints_deg'])) <= 9.+1e-12
        previous=point
    assert targets[-1]['step_id'] == 32  # Input path was not mutated.
    with pytest.raises(ValueError, match='budget'):
        motion_limited_waypoints([dict(targets[0],step_id=2999)],baseline,9.)


def test_fixed_motion_cap_uses_lower_station_limit(tmp_path):
    provider=adapter(tmp_path,gateway_max_step_deg=9.)
    assert provider.public_config()['max_joint_step_deg'] == 20.
    assert provider.public_config()['effective_joint_step_deg'] == 9.


def test_hosted_worker_slot_is_deferred_until_active_and_released_on_stop(tmp_path):
    pool = threading.BoundedSemaphore(1)
    first = adapter(tmp_path/'first', worker_pool=pool)
    second = adapter(tmp_path/'second', worker_pool=pool)
    waiting = threading.Event()
    errors = []
    try:
        for policy in (first, second):
            policy.start_preparation(lambda: False)
            assert policy._worker is None and policy._preparation is None
        first.wait_ready(lambda: False)
        def ready():
            waiting.set()
            try:
                second.wait_ready(lambda: False)
            except RuntimeError as error:
                errors.append(str(error))
        thread = threading.Thread(target=ready)
        thread.start();assert waiting.wait(1)
        time.sleep(.15)
        assert second._worker is None
        first.close_transport()
        thread.join(2)
        assert not thread.is_alive() and not errors
        assert first._worker.closed.is_set() and second._worker is not None
    finally:
        first.close_transport();second.close_transport()
    assert pool.acquire(blocking=False)
    pool.release()


def test_stop_cancels_hosted_slot_wait_without_starting_another_sdk(tmp_path):
    pool = threading.BoundedSemaphore(1)
    assert pool.acquire(blocking=False)
    policy = adapter(tmp_path, worker_pool=pool)
    errors = []
    def ready():
        try:
            policy.wait_ready(lambda: False)
        except RuntimeError as error:
            errors.append(str(error))
    thread = threading.Thread(target=ready)
    try:
        policy.start_preparation(lambda: False)
        thread.start();time.sleep(.15)
        policy.close_transport();thread.join(1)
        assert not thread.is_alive() and errors
        assert policy._worker is None
        assert not pool.acquire(blocking=False)  # This adapter never owned the slot.
    finally:
        pool.release();policy.close_transport()


def test_real_camera_tick_encoding_identity_and_freshness(tmp_path):
    provider = adapter(tmp_path)
    provider._prompt = 'move'
    tick = provider._capture_tick()
    assert set(tick['frames']) == {'video.overhead', 'video.wrist_l', 'video.wrist_r'}
    with Image.open(io.BytesIO(base64.b64decode(tick['frames']['video.overhead']))) as image:
        assert image.size == (320, 176)
    provider.observation_source = lambda: dict(observation(), jetson_id='another-robot')
    with pytest.raises(ValueError, match='identity'): provider._capture_tick()
    provider.observation_source = lambda: dict(observation(), observed_at=time.time() - 20)
    with pytest.raises(ValueError, match='fresh'): provider._capture_tick()


def test_history_continues_during_inference_and_prompt_resets(tmp_path):
    provider = adapter(tmp_path)
    try:
        provider.wait_ready(lambda: False)  # Also covers readiness before explicit preparation.
        provider._worker.hold = threading.Event()
        outcome = []
        thread = threading.Thread(target=lambda: outcome.append(provider.build_trajectory('first', observation(), 0)))
        thread.start()
        deadline = time.monotonic() + 3
        while not any(c == 'predict' for c, _ in provider._worker.calls):
            assert time.monotonic() < deadline
            time.sleep(.01)
        time.sleep(.45)
        with provider._changed:
            assert len(provider._history) >= 3
        provider._worker.hold.set()
        thread.join(2)
        assert len(outcome[0]) >= 24  # Initial measured-to-target transition can add a step.
        provider.build_trajectory('second', observation(), 24)
        assert any(c == 'reset' for c, _ in provider._worker.calls)
        ticks = [payload['ticks'] for c, payload in provider._worker.calls if c == 'predict'][-1]
        assert all(tick['observation']['prompt'] == 'second' for tick in ticks)
        assert 'private-file' not in str(provider.public_config())
    finally:
        provider.close_transport()


def test_stop_releases_worker_and_discards_late_prediction(tmp_path):
    provider = adapter(tmp_path)
    cancelled = threading.Event()
    provider.start_preparation(cancelled.is_set)
    provider.wait_ready(cancelled.is_set)
    provider._worker.hold = threading.Event()
    errors = []
    def build():
        try: provider.build_trajectory('move', observation(), 0)
        except RuntimeError as error: errors.append(str(error))
    thread = threading.Thread(target=build)
    thread.start()
    deadline = time.monotonic() + 3
    while not any(c == 'predict' for c, _ in provider._worker.calls):
        assert time.monotonic() < deadline
        time.sleep(.01)
    cancelled.set()
    assert provider._worker.closed.wait(1)
    thread.join(2)
    assert errors and 'cancelled' in errors[0]


def test_camera_failure_is_reported_instead_of_reusing_old_history(tmp_path, monkeypatch):
    monkeypatch.setattr('remote_yam.dream_policy.OBSERVATION_RECOVERY_S', .01)
    provider = adapter(tmp_path)
    provider.observation_source = lambda: dict(observation(), observed_at=0)
    try:
        with pytest.raises(RuntimeError, match='capture failed'):
            provider.build_trajectory('move', observation(), 0)
    finally:
        provider.close_transport()


@pytest.mark.parametrize('field,value', [('left_joints_deg',[0]*5),
    ('right_joints_deg',[float('nan')]*6),('left_gripper',1.01),
    ('right_gripper','private-value'),('observed_at',float('nan'))])
def test_invalid_measured_fields_have_specific_safe_permanent_diagnostics(tmp_path, field, value):
    provider = adapter(tmp_path)
    provider.observation_source = lambda: dict(observation(), **{field:value})
    with pytest.raises(DreamObservationError) as caught:
        provider._capture_tick()
    assert caught.value.field == field and not caught.value.retryable
    assert field in str(caught.value) and 'private-value' not in str(caught.value)


@pytest.mark.parametrize('gap', ['missing_gripper','stale_state'])
def test_transient_observation_gap_recovers_with_real_new_sample(tmp_path, gap):
    provider = adapter(tmp_path)
    reads, events = [], []
    def source():
        current = observation()
        reads.append(current)
        if len(reads) == 1:
            current.update(left_gripper=None) if gap == 'missing_gripper' else current.update(observed_at=0)
        return current
    provider.observation_source = source
    provider.interaction_sink = lambda kind, *args, **kwargs: events.append(kind)
    try:
        points = provider.build_trajectory('move', observation(), 0)
        assert points and len(reads) >= 2
        ticks = next(payload['ticks'] for command,payload in provider._worker.calls if command == 'predict')
        assert all(tick['observation']['state.left_gripper'] == [.3] for tick in ticks)
        assert all(tick['observed_at'] > 0 for tick in ticks)
        deadline = time.monotonic() + 1
        while 'observation_recovered' not in events:
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert 'observation_retry' in events
        assert provider._failure is None
    finally:
        provider.close_transport()


def test_persistent_missing_measurement_times_out_without_inference(tmp_path, monkeypatch):
    monkeypatch.setattr('remote_yam.dream_policy.OBSERVATION_RECOVERY_S', .25)
    provider = adapter(tmp_path)
    provider.observation_source = lambda: dict(observation(), right_gripper=None)
    began = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match='right_gripper.*recovery timed out'):
            provider.build_trajectory('move', observation(), 0)
        assert time.monotonic() - began < 2
        assert not any(command == 'predict' for command,_ in provider._worker.calls)
        assert not provider._history
    finally:
        provider.close_transport()


def test_identity_change_is_immediate_and_does_not_reuse_history(tmp_path):
    provider = adapter(tmp_path)
    reads = []
    def source():
        reads.append(1)
        return dict(observation(), jetson_id='another-robot')
    provider.observation_source = source
    try:
        with pytest.raises(RuntimeError, match='robot identity changed'):
            provider.build_trajectory('move', observation(), 0)
        assert len(reads) == 1 and not provider._history
        assert not any(command == 'predict' for command,_ in provider._worker.calls)
    finally:
        provider.close_transport()


def test_invalid_feedback_during_inference_discards_late_prediction(tmp_path):
    provider = adapter(tmp_path)
    invalid = threading.Event()
    provider.observation_source = lambda: dict(observation(), left_gripper=float('nan')) if invalid.is_set() else observation()
    results, errors = [], []
    def build():
        try:
            results.append(provider.build_trajectory('move', observation(), 0))
        except RuntimeError as error:
            errors.append(str(error))
    try:
        provider.wait_ready(lambda: False)
        provider._worker.hold = threading.Event()
        thread = threading.Thread(target=build)
        thread.start()
        deadline = time.monotonic() + 2
        while not any(command == 'predict' for command,_ in provider._worker.calls):
            assert time.monotonic() < deadline
            time.sleep(.01)
        invalid.set()
        while provider._failure is None:
            assert time.monotonic() < deadline
            time.sleep(.01)
        provider._worker.hold.set()
        thread.join(1)
        assert not thread.is_alive() and not results
        assert errors and 'left_gripper' in errors[0]
    finally:
        provider.close_transport()


def test_stop_interrupts_observation_recovery_without_inference(tmp_path):
    provider = adapter(tmp_path)
    waiting = threading.Event()
    provider.interaction_sink = lambda *args,**kwargs: waiting.set()
    provider.observation_source = lambda: dict(observation(), left_gripper=None)
    errors = []
    def build():
        try: provider.build_trajectory('move', observation(), 0)
        except RuntimeError as error: errors.append(str(error))
    thread = threading.Thread(target=build)
    thread.start()
    try:
        assert waiting.wait(2)
        provider.close_transport()
        thread.join(1)
        assert not thread.is_alive() and errors and 'cancelled' in errors[0]
        assert not any(command == 'predict' for command,_ in provider._worker.calls)
    finally:
        provider.close_transport()


def test_decode_failure_has_camera_identity_without_exposing_exception_text(tmp_path):
    provider = adapter(tmp_path)
    class BadCameras:
        def capture_for_policy(self, *args, **kwargs):
            return [CameraFrame(name,b'private-bad-pixels',time.time()) for name in ('top','left','right')]
    provider.camera_source = BadCameras()
    with pytest.raises(DreamObservationError) as caught:
        provider._capture_tick()
    assert caught.value.field == 'camera_top' and not caught.value.retryable
    assert 'top camera image decoding' in str(caught.value)
    assert 'private-bad-pixels' not in str(caught.value)


def test_completed_target_is_passed_to_sdk_instead_of_guessing_from_measured_lag(tmp_path):
    provider = adapter(tmp_path)
    try:
        points = provider.build_trajectory('move', observation(), 0)
        first = [payload for command, payload in provider._worker.calls if command == 'predict'][-1]
        assert first.get('commanded') is None
        provider.trajectory_completed(dict(observation(), step_id=24), len(points))
        provider.build_trajectory('move', observation(), 24)
        second = [payload for command, payload in provider._worker.calls if command == 'predict'][-1]
        assert second['commanded']['q_l_chunk'] == pytest.approx([.047]*6+[.2])
        assert second['commanded']['q_r_chunk'] == pytest.approx([-.047]*6+[.8])
        # Prompt reset starts a fresh SDK episode, with no previous chunk to join.
        provider.build_trajectory('new task', observation(), 48)
        reset = [payload for command, payload in provider._worker.calls if command == 'predict'][-1]
        assert reset.get('commanded') is None
        assert provider.public_config()['action_space'] == 'eef'
    finally:
        provider.close_transport()


def test_worker_process_protocol_closes_session_and_hides_key(tmp_path, monkeypatch):
    fake = tmp_path / 'sdk'
    fake.mkdir()
    (fake / 'dream.py').write_text('''
import os
from pathlib import Path
__version__ = '1.0.0'
class DreamClient:
    last_timing = {'rtt_ms': 600}
    def policy(self, config):
        assert config['_record'] is False
        assert config['ik'] == {'arm':'yam','head':'eef','solve':'traj'}
    def set_observation(self, frames, observation, timestamp):
        assert set(frames) == {'video.overhead','video.wrist_l','video.wrist_r'}
        assert observation['state.left_arm'].dtype.name == 'float32'
    def get_action(self, *, commanded=None):
        if commanded is not None:
            assert commanded['q_l_chunk'] == [0]*6+[.3]
        return {'q_l_chunk': [[0]*6+[.3]]*48, 'q_r_chunk': [[0]*6+[.7]]*48}
    def reset_episode(self): pass
    def close(self): Path(os.environ['FAKE_CLOSE_MARKER']).write_text('closed')
''')
    marker = tmp_path / 'closed'
    monkeypatch.setenv('PYTHONPATH', str(fake))
    monkeypatch.setenv('FAKE_CLOSE_MARKER', str(marker))
    worker = DreamWorker(sys.executable, tmp_path / 'private-credentials', tmp_path / 'cache')
    try:
        response = worker.call('configure', checkpoint='dreamlabs/dream-1-beta')
        assert response['ok'], response
        tick = dict(timestamp=1, frames={k:'jpeg' for k in ('video.overhead','video.wrist_l','video.wrist_r')},
                    observation=state_input(observation(), 'move'))
        result = worker.call('predict', ticks=[tick])
        assert result['ok'] and len(action_waypoints(result['result']['action'], 0)) == 24
        result = worker.call('predict', ticks=[dict(tick, timestamp=2)],
            commanded={'q_l_chunk':[0]*6+[.3], 'q_r_chunk':[0]*6+[.7]})
        assert result['ok'], result
        assert 'private-credentials' not in str(result)
    finally:
        worker.close()
    assert marker.read_text() == 'closed' and worker.process.poll() == 0


def test_provider_registration_is_yam_only_and_public_metadata_has_no_secrets(tmp_path):
    from playground import HostedRunner, RequestError
    credentials = tmp_path / 'private-credentials'
    credentials.write_text('DREAM_API_KEY=secret-fixture-value\n')
    app = HostedRunner(public_origin='http://127.0.0.1:8799', development=True, session_api=None,
        camera_origin='http://127.0.0.1:8089',
        dream_credentials_file=str(credentials), dream_python=sys.executable)
    assert set(app.dream_providers) == {'dream', 'dream_flash'}
    assert app.dream_providers['dream']['motion_cap']['gateway_step_deg'] == pytest.approx(9.)
    assert 'secret-fixture-value' not in str(app.dream_providers)
    assert str(credentials) not in str(app.dream_providers)
    p = app.extra_providers['dream']('dreamlabs/dream-1-beta', tmp_path / 'run')
    assert p.model == 'dreamlabs/dream-1-beta' and p._preparation is None
    with pytest.raises(RequestError): app.extra_providers['dream']('arbitrary-model', tmp_path)
    other = HostedRunner(public_origin='http://127.0.0.1:8798', development=True, session_api=None,
        camera_origin='http://127.0.0.1:8089',
        hardware='so101', joint_counts=(5,0), camera_names=('front',),
        dream_credentials_file=str(credentials), dream_python=sys.executable)
    assert not other.dream_providers


def test_run_payload_cannot_override_fixed_motion_cap(tmp_path, monkeypatch):
    from playground import HostedRunner
    from remote_yam.session import MockSessionAPI
    from unittest.mock import Mock
    credentials=tmp_path/'credentials';credentials.write_text('DREAM_API_KEY=fixture\n')
    app=HostedRunner(public_origin='http://127.0.0.1:8799',development=True,session_api=None,
        camera_origin='http://127.0.0.1:8089',api_factory=lambda:MockSessionAPI(auto_activate=False),
        dream_credentials_file=str(credentials),dream_python=sys.executable)
    _,visitor=app.new_visitor()
    factory=app.extra_providers['dream'];providers=[]
    def capture(model,directory):
        provider=factory(model,directory);providers.append(provider);return provider
    app.extra_providers['dream']=capture
    monkeypatch.setattr(visitor.controller,'join_and_run',Mock(return_value={'status':'queued'}))
    app.launch(visitor,dict(provider='dream',model='dreamlabs/dream-1-beta',prompt='move',
                            dream_max_joint_step_deg=9999))
    assert providers[0].public_config()['max_joint_step_deg']==20.
    assert providers[0].public_config()['effective_joint_step_deg']==9.
