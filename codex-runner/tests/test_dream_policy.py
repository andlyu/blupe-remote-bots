import base64
import io
import math
import threading
import time
import sys
import json
import importlib.util
from pathlib import Path

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


def test_recovery_generation_discards_capture_already_in_flight(tmp_path):
    provider = adapter(tmp_path)
    provider._prompt = 'same run'
    old_started, old_done = threading.Event(), threading.Event()
    fresh_started, fresh_done = threading.Event(), threading.Event()
    count = []
    def capture():
        count.append(1)
        old = len(count) == 1
        (old_started if old else fresh_started).set()
        assert (old_done if old else fresh_done).wait(2)
        return dict(timestamp=time.monotonic(), observed_at=time.time(),
                    observation={'prompt': 'same run', 'version': 'old' if old else 'fresh'})
    provider._capture_tick = capture
    thread = threading.Thread(target=provider._collect)
    try:
        thread.start(); assert old_started.wait(1)
        with provider._changed:
            provider._history_generation += 1
            provider._history.clear()
        old_done.set(); assert fresh_started.wait(1)
        with provider._changed:
            assert not provider._history
        fresh_done.set()
        with provider._changed:
            assert provider._changed.wait_for(lambda: bool(provider._history), timeout=1)
            assert all(tick['observation']['version'] == 'fresh' for tick in provider._history)
    finally:
        provider.close_transport(); old_done.set(); fresh_done.set(); thread.join(2)


def test_recovery_feedback_watermark_uses_the_robot_clock(tmp_path):
    from types import SimpleNamespace
    provider = adapter(tmp_path)
    provider._prompt = 'same run'
    observed_at = time.time()-1.5  # Fresh feedback can use a slightly offset clock.
    provider.observation_source = lambda: dict(observation(), observed_at=observed_at)
    provider._worker = SimpleNamespace(recover=lambda **kwargs: None, close=lambda: None)
    assert provider._recover_worker(72, 'worker_timeout') == observed_at
    assert provider._history_generation == 1 and not provider._history
    provider.close_transport()


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


@pytest.mark.parametrize('problem', [None,'identity','missing_gripper','stale_state','stale_frame'])
def test_camera_retry_pairs_new_images_with_remeasured_state(tmp_path, monkeypatch, problem):
    clock = [100.]
    monkeypatch.setattr('remote_yam.dream_policy.time.time', lambda:clock[0])
    provider = adapter(tmp_path)
    reads, events = [], []
    def source():
        measured = dict(observation(), left_joints_deg=[len(reads)]*6)
        if reads:
            if problem == 'identity': measured['jetson_id']='another-robot'
            if problem == 'missing_gripper': measured['left_gripper']=None
            if problem == 'stale_state': measured['observed_at']=100.
        reads.append(measured)
        return measured
    class RecoveringCameras(Cameras):
        def capture_for_policy(self, observed, **kwargs):
            kwargs['on_event']('camera_retry','Waiting for next left frame',
                              dict(camera='left',attempt=1,cause='HTTP 503'))
            clock[0] = 106.
            frames=super().capture_for_policy(observed)
            if problem == 'stale_frame':
                frames[0]=CameraFrame(frames[0].name,frames[0].jpeg,100.)
            return frames
    provider.observation_source=source
    provider.camera_source=RecoveringCameras()
    provider.interaction_sink=lambda kind,*args,**kwargs:events.append(kind)
    if problem:
        with pytest.raises(DreamObservationError) as caught:
            provider._capture_tick()
        assert caught.value.field == dict(identity='jetson_id',missing_gripper='left_gripper',
                                          stale_state='observed_at',stale_frame='camera_right')[problem]
    else:
        tick=provider._capture_tick()
        assert tick['observed_at']==106.
        assert tick['observation']['state.left_arm']==pytest.approx([math.radians(1)]*6)
        assert 'observation_refreshed' in events and 'camera_retry' in events
    assert len(reads)==2


def test_camera_exhaustion_names_actual_role_and_http_status(tmp_path):
    provider=adapter(tmp_path)
    class FailedCameras:
        def capture_for_policy(self, observed, **kwargs):
            kwargs['on_event']('camera_failure','Camera failed',
                dict(camera='left',attempt=10,cause='HTTP 503',http_status=503))
            raise RuntimeError('private upstream detail must not escape')
    provider.camera_source=FailedCameras()
    with pytest.raises(DreamObservationError) as caught:
        provider._capture_tick()
    assert caught.value.field=='camera_left'
    assert 'left camera capture failed (HTTP 503)' in str(caught.value)
    assert 'private upstream' not in str(caught.value)


def expired_reply():
    return dict(ok=False,error_type='DreamSessionExpired',code='DA-0001',reason='expired',retryable=False)


class SessionWorker(Worker):
    def __init__(self,*args):
        super().__init__(*args)
        self.responses=[]

    def call(self,command,**kwargs):
        result=super().call(command,**kwargs)
        return self.responses.pop(0) if command=='predict' and self.responses else result


def test_session_replacement_requeries_new_input_without_replaying_or_resetting(tmp_path):
    provider=adapter(tmp_path)
    provider.worker_factory=SessionWorker
    try:
        points=provider.build_trajectory('move',observation(),0)
        provider.trajectory_completed(observation(),len(points))
        completed=provider._commanded
        provider._worker.responses=[expired_reply()]
        following=provider.build_trajectory('move',observation(),len(points))
        calls=[payload for command,payload in provider._worker.calls if command=='predict']
        assert len(calls)==3
        assert calls[2]['ticks'][-1]['timestamp']>calls[1]['ticks'][-1]['timestamp']
        assert calls[2]['commanded']==completed
        assert following[0]['step_id']==len(points)
        assert not any(command=='reset' for command,_ in provider._worker.calls)
    finally:
        provider.close_transport()


@pytest.mark.parametrize('replies,expected', [([expired_reply(),expired_reply()],2),
    ([dict(ok=False,error_type='DreamAuthError',code='DA-1000',reason='disabled')],1)])
def test_prediction_recovery_is_bounded_and_auth_errors_do_not_retry(tmp_path,replies,expected):
    provider=adapter(tmp_path)
    provider.worker_factory=SessionWorker
    try:
        provider.wait_ready(lambda:False)
        provider._worker.responses=replies
        with pytest.raises(RuntimeError,match='Dream request failed .*Dream'):
            provider.build_trajectory('move',observation(),0)
        assert len([c for c,_ in provider._worker.calls if c=='predict'])==expected
    finally:
        provider.close_transport()


def test_stop_cancels_session_recovery_before_another_prediction(tmp_path):
    provider=adapter(tmp_path)
    provider.worker_factory=SessionWorker
    cancelled=threading.Event()
    provider.cancelled=cancelled.is_set
    provider.interaction_sink=lambda kind,*args,**kwargs:cancelled.set() if kind=='model_progress' else None
    try:
        provider.wait_ready(lambda:False)
        provider._worker.responses=[expired_reply()]
        with pytest.raises(RuntimeError,match='cancelled'):
            provider.build_trajectory('move',observation(),0)
        assert len([c for c,_ in provider._worker.calls if c=='predict'])==1
    finally:
        provider.close_transport()


def test_worker_error_metadata_does_not_expose_private_text_or_arbitrary_reason(tmp_path,monkeypatch):
    monkeypatch.setenv('DREAM_WORK_DIR',str(tmp_path))
    path=Path(__file__).parents[1]/'src/remote_yam/dream_worker.py'
    spec=importlib.util.spec_from_file_location('dream_worker_diagnostics',path)
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    class DreamSessionExpired(RuntimeError):
        code='DA-0001';reason='expired';retryable=False;retry_after_s=None
    error=DreamSessionExpired('private credential and server identifiers')
    reply=worker.error_response(error)
    assert reply==dict(ok=False,error_type='DreamSessionExpired',code='DA-0001',reason='expired',
                       retryable=False,retry_after_s=None)
    assert 'private credential' not in json.dumps(reply)
    error.code='private-code';error.reason='private-reason';error.retry_after_s=float('nan')
    reply=worker.error_response(error)
    assert reply['code'] is None and reply['reason'] is None and reply['retry_after_s'] is None
    assert 'private-' not in json.dumps(reply,allow_nan=False)


@pytest.mark.parametrize('message,cause,category,status', [
    ('inference reply from private-endpoint is not JSON (HTTP 502); is the correct DreamAPI gateway running there?',
     json.JSONDecodeError('private-body', '', 0), 'non_json_reply', 502),
    ('inference reply carries no status envelope; is the correct DreamAPI gateway running?',
     None, 'missing_status_envelope', None),
    ('private-endpoint unreachable: private-details', ConnectionResetError('private-address'),
     'connection_failure', None),
    ('private-body with unknown SDK text', None, 'other_protocol_error', None),
])
def test_sdk_protocol_raise_conditions_are_classified_without_private_text(tmp_path, monkeypatch,
                                                                         message, cause, category, status):
    monkeypatch.setenv('DREAM_WORK_DIR', str(tmp_path))
    path = Path(__file__).parents[1]/'src/remote_yam/dream_worker.py'
    spec = importlib.util.spec_from_file_location('dream_protocol_diagnostics', path)
    worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
    class DreamProtocolError(RuntimeError):
        pass
    error = DreamProtocolError(message); error.__cause__ = cause
    reply = worker.error_response(error, phase='predict', timing={
        'rtt_ms': 31000, 'response_bytes': 17, 'request_bytes': 40000,
        'gateway_ms': float('nan'), 'network_ms': -1, 'secret': 'private-timing'})
    assert reply['protocol_category'] == category and reply['http_status'] == status
    assert reply['phase'] == 'predict'
    assert reply['timing'] == dict(rtt_ms=31000, response_bytes=17, request_bytes=40000)
    assert 'private-' not in json.dumps(reply, allow_nan=False)


def test_protocol_failure_reaches_journal_and_user_without_retry(tmp_path):
    provider = adapter(tmp_path)
    provider.worker_factory = SessionWorker
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append((kind, details))
    try:
        provider.wait_ready(lambda: False)
        provider._worker.responses = [dict(ok=False, error_type='DreamProtocolError',
            protocol_category='non_json_reply', http_status=502, cause_type='JSONDecodeError',
            phase='predict', timing={'rtt_ms': 31000}, retryable=False)]
        with pytest.raises(RuntimeError, match=r'non_json_reply; HTTP 502'):
            provider.build_trajectory('move', observation(), 0)
        failure = [details for kind, details in events if kind == 'model_failure'][0]
        assert failure['http_status'] == 502 and failure['phase'] == 'predict'
        assert failure['timing'] == {'rtt_ms': 31000}
        assert len([c for c, _ in provider._worker.calls if c == 'predict']) == 1
    finally:
        provider.close_transport()


@pytest.mark.parametrize('failure,category,http_status', [
    ('non_json', 'non_json_reply', 502),
    ('envelope', 'missing_status_envelope', None),
    ('connection', 'connection_failure', None),
])
def test_real_worker_bridge_preserves_warmup_then_sdk_protocol_failure(tmp_path, monkeypatch,
                                                                     failure, category, http_status):
    """Exercise the adapter + actual worker subprocess, with a controlled SDK.

    These are synthetic failure fixtures, not a successful live inference test.
    The known exception branches match pinned SDK 1.0.0. No robot API exists here.
    """
    sdk = tmp_path/'controlled_sdk'; sdk.mkdir()
    (sdk/'dream.py').write_text('''
import os
__version__ = '1.0.0'
class DreamServerError(RuntimeError):
    code='DA-2000'; reason='pool_warming'; retryable=True; retry_after_s=0
class DreamProtocolError(RuntimeError): pass
class DreamClient:
    last_timing = None
    def __init__(self): self.calls=0
    def policy(self, config): pass
    def close(self): pass
    def set_observation(self, frames, state, timestamp):
        assert set(frames)=={'video.overhead','video.wrist_l','video.wrist_r'}
        assert len(state['state.left_arm'])==len(state['state.right_arm'])==6
    def get_action(self, commanded=None):
        self.calls+=1
        if self.calls==1: raise DreamServerError('private warmup endpoint')
        self.last_timing={'rtt_ms':31000,'response_bytes':17,'secret':'private timing'}
        mode=os.environ['DREAM_BRIDGE_FAILURE']
        if mode=='non_json':
            raise DreamProtocolError('inference reply from private-host is not JSON (HTTP 502); is the correct DreamAPI gateway running there?')
        if mode=='envelope':
            raise DreamProtocolError('inference reply carries no status envelope; is the correct DreamAPI gateway running?')
        raise DreamProtocolError('private connection detail') from ConnectionResetError('private address')
''')
    monkeypatch.setenv('PYTHONPATH', str(sdk))
    # DreamWorker intentionally strips DREAM_* overrides; use a general fixture
    # variable so the bridge retains the same production environment filtering.
    module = sdk/'dream.py'
    module.write_text(module.read_text().replace('DREAM_BRIDGE_FAILURE', 'TEST_BRIDGE_FAILURE'))
    monkeypatch.setenv('TEST_BRIDGE_FAILURE', failure)
    provider = adapter(tmp_path/'bridge')
    provider.robot_id = 'robot-ba8413962083809c'
    provider.observation_source = lambda: dict(observation(), jetson_id=provider.robot_id)
    provider.python = sys.executable
    provider.worker_factory = DreamWorker
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append((kind, message, details))
    try:
        with pytest.raises(RuntimeError, match=category):
            provider.build_trajectory('synthetic fixture', observation(), 0)
        assert any(kind=='model_progress' and message=='Dream model is warming'
                   for kind, message, _ in events)
        detail = next(d for kind, _, d in events if kind=='model_failure')
        assert sum(kind=='model_failure' for kind, _, _ in events)==1
        assert detail['protocol_category']==category and detail['http_status']==http_status
        assert detail['phase']=='predict'
        assert detail['timing']==dict(rtt_ms=31000, response_bytes=17)
        sdk_stages = {d.get('stage') for kind, _, d in events if kind=='policy_timing'}
        assert {'sdk_import','sdk_client_init','sdk_configure','sdk_observation_update','sdk_get_action'} <= sdk_stages
        assert 'private' not in json.dumps(events)
        worker = provider._worker
    finally:
        provider.close_transport()
    assert worker.process.poll() is not None


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


@pytest.mark.parametrize('configured', [False, True])
def test_worker_honors_service_compilation_cache_and_keeps_private_work_dirs(tmp_path, monkeypatch, configured):
    sdk = tmp_path/'sdk'; sdk.mkdir()
    (sdk/'dream.py').write_text('''
import json, os
from pathlib import Path
__version__='1.0.0'
class DreamClient:
    def policy(self, config):
        with open(os.environ['TEST_CACHE_RECEIPT'], 'a') as out:
            out.write(json.dumps({'cache':os.environ['JAX_COMPILATION_CACHE_DIR'],
                                  'work':os.environ['DREAM_WORK_DIR']})+'\\n')
    def close(self): pass
''')
    monkeypatch.setenv('PYTHONPATH', str(sdk))
    receipt = tmp_path/'cache-paths.jsonl'
    monkeypatch.setenv('TEST_CACHE_RECEIPT', str(receipt))
    shared = tmp_path/'persistent compilation cache'
    if configured:
        monkeypatch.setenv('JAX_COMPILATION_CACHE_DIR', str(shared))
    else:
        monkeypatch.delenv('JAX_COMPILATION_CACHE_DIR', raising=False)
    for visitor in ('visitor-one', 'visitor-two'):
        directory = tmp_path/visitor
        worker = DreamWorker(sys.executable, tmp_path/'synthetic-credentials', directory)
        try:
            assert worker.call('configure', checkpoint='dreamlabs/dream-1-beta')['ok']
        finally:
            worker.close()
        assert worker.process.poll() is not None
    rows = [json.loads(line) for line in receipt.read_text().splitlines()]
    assert [row['work'] for row in rows] == [str(tmp_path/v) for v in ('visitor-one','visitor-two')]
    assert [row['cache'] for row in rows] == ([str(shared)]*2 if configured else
        [str(tmp_path/v/'jax') for v in ('visitor-one','visitor-two')])


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


@pytest.mark.parametrize('cause_name,family', [
    ('SSLEOFError','tls'),('SSLZeroReturnError','tls'),('SSLWantReadError','tls'),
    ('SSLCertVerificationError','tls'),('CannotSendRequest','http'),
    ('ResponseNotReady','http'),('LineTooLong','http'),('ConnectionAbortedError','network'),
])
def test_protocol_diagnostics_retain_bounded_ssl_http_subclasses(tmp_path,monkeypatch,cause_name,family):
    import ssl,http.client
    path=Path(__file__).parents[1]/'src/remote_yam/dream_worker.py'
    monkeypatch.setenv('DREAM_WORK_DIR',str(tmp_path))
    spec=importlib.util.spec_from_file_location('bounded_protocol',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    klass=getattr(ssl,cause_name,None) or getattr(http.client,cause_name,None) or getattr(__import__('builtins'),cause_name)
    cause=klass('private endpoint, key and payload')
    error=type('DreamProtocolError',(RuntimeError,),{})('private SDK endpoint text');error.__cause__=cause
    reply=module.error_response(error,phase='predict')
    assert reply['protocol_category']=='connection_failure'
    assert reply['cause_type']==cause_name and reply['cause_family']==family
    assert reply['http_status'] is None and 'private' not in json.dumps(reply)


def test_protocol_context_and_static_trace_hide_request_locals(tmp_path,monkeypatch):
    import http.client,ssl
    monkeypatch.setenv('DREAM_WORK_DIR',str(tmp_path))
    spec=importlib.util.spec_from_file_location('trace_protocol',Path(__file__).parents[1]/'src/remote_yam/dream_worker.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    class Socket:
        def sendall(self,value):raise ssl.SSLEOFError(8,'private TLS endpoint')
    connection=http.client.HTTPConnection('private-host');connection.sock=Socket()
    try:
        try:connection.request('POST','/private-route',body='private-image',headers={'Authorization':'private-key'})
        except Exception:raise type('DreamProtocolError',(RuntimeError,),{})('private wrapper') from None
    except Exception as error:
        assert error.__cause__ is None
        reply=module.error_response(error,phase='predict')
    assert reply['cause_type']=='SSLEOFError' and reply['cause_errno']==8
    assert reply['transport_stage']=='request_send'
    assert 1<=len(reply['protocol_trace'])<=8
    assert all(r['module']=='http.client' and set(r)=={'module','function','line'} for r in reply['protocol_trace'])
    assert 'private' not in json.dumps(reply) and 'Authorization' not in json.dumps(reply)


def test_unknown_oserror_subtype_cannot_export_arbitrary_class_or_reason(tmp_path,monkeypatch):
    monkeypatch.setenv('DREAM_WORK_DIR',str(tmp_path))
    spec=importlib.util.spec_from_file_location('unknown_protocol',Path(__file__).parents[1]/'src/remote_yam/dream_worker.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cause=type('PrivateHostAndKey',(OSError,),{'reason':['private']})(103,'private-host')
    error=type('DreamProtocolError',(RuntimeError,),{})('private');error.__cause__=cause
    reply=module.error_response(error,phase='predict')
    assert reply['cause_type']=='OSError' and reply['cause_family']=='network'
    assert reply['cause_reason'] is None and 'private' not in json.dumps(reply).lower()


@pytest.mark.parametrize('fail',[False,True])
def test_worker_reuses_http_and_cleans_failed_channel_without_replaying(tmp_path,monkeypatch,fail):
    sdk=tmp_path/'sdk';sdk.mkdir();trace=tmp_path/'transport.jsonl'
    (sdk/'dream.py').write_text('''
import json,os,ssl
from types import SimpleNamespace
__version__='1.0.0'
class DreamProtocolError(RuntimeError):pass
class Channel:
    connected=False
    def _drop(self):self.connected=False
class DreamClient:
    last_timing={'rtt_ms':1,'response_bytes':0}
    def __init__(self):
        self._policy=SimpleNamespace(_transport=Channel());self.session_id=None;self.frames=[]
    def record(self,kind,**values):
        with open(os.environ['TEST_HTTP_TRACE'],'a') as out:out.write(json.dumps(dict(kind=kind,**values))+'\\n')
    def policy(self,config):self.record('policy')
    def set_observation(self,frames,state,timestamp):self.frames.append(state['prompt'])
    def get_action(self,commanded=None):
        channel=self._policy._transport
        self.record('predict',session_id=self.session_id,frames=list(self.frames),connected=channel.connected)
        if os.environ['TEST_HTTP_FAIL']=='yes' and len(self.frames)==2:
            try:raise ssl.SSLEOFError(8,'private address and payload')
            except ssl.SSLError as cause:raise DreamProtocolError('private endpoint') from cause
        channel.connected=True;self.session_id='same-model-session'
        return {key:[[0.]*6+[.5] for _ in range(48)] for key in ['q_l_chunk','q_r_chunk']}
    def reset_episode(self):
        self._policy._transport.connected=True
        self.frames=[];self.session_id=None;self.record('reset')
    def close(self):pass
''')
    monkeypatch.setenv('PYTHONPATH',str(sdk));monkeypatch.setenv('TEST_HTTP_TRACE',str(trace))
    monkeypatch.setenv('TEST_HTTP_FAIL','yes' if fail else 'no')
    worker=DreamWorker(sys.executable,tmp_path/'synthetic-credentials',tmp_path/'worker')
    try:
        assert worker.call('configure',checkpoint='dreamlabs/dream-1-beta')['ok']
        def predict(n):return worker.call('predict',ticks=[dict(timestamp=n,frames={},observation={'prompt':str(n)})])
        if fail:
            assert predict(1)['ok']
            reply=predict(2)
            assert not reply['ok'] and reply['cause_type']=='SSLEOFError'
            assert reply['protocol_category']=='connection_failure'
            assert reply['http_connection_policy']=='reuse_until_reset_or_failure'
            assert 'private' not in json.dumps(reply)
            assert len(trace.read_text().splitlines())==3  # policy + two calls, no retry
            assert predict(3)['ok']
        else:
            assert all(predict(n)['ok'] for n in (1,2,3))
            assert worker.call('reset')['ok']
            assert predict(4)['ok']
    finally:worker.close()
    records=[json.loads(line) for line in trace.read_text().splitlines()]
    predictions=[r for r in records if r['kind']=='predict']
    assert len([r for r in records if r['kind']=='policy'])==1
    assert len(predictions)==(3 if fail else 4)  # No extra inference retry.
    assert [r['connected'] for r in predictions]==([False,True,False] if fail else [False,True,True,False])
    if not fail:
        assert [r['session_id'] for r in predictions]==[None,'same-model-session','same-model-session',None]
        assert [r['frames'] for r in predictions]==[['1'],['1','2'],['1','2','3'],['4']]
