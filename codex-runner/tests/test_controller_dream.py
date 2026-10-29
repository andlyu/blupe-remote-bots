import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from remote_yam.controller_dream import LoopbackControllerInputs, NativeControllerDream


def status():
    return dict(backend='physical_i2rt', mode='READY', feedback_available=True,
        api={'session_id': None}, auto_queue={'enabled': False, 'running': False},
        dataset={'robot_id': 'robohouse'}, joints=[.1]*12, left_gripper=.3, right_gripper=.7)


def source(value):
    inputs = LoopbackControllerInputs(robot_id='robohouse', cameras=dict(left=6, top=12, right=18))
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps(value).encode()
    inputs.opener = SimpleNamespace(open=lambda *args, **kwargs: Response())
    return inputs


def test_local_measured_units_and_camera_aliases():
    inputs = source(status())
    result = inputs()
    assert result['left_joints_deg'] == pytest.approx([5.7295779513]*6)
    assert result['right_gripper'] == .7
    assert result['images']['left']['url'] == 'http://127.0.0.1:8089/6/snapshot.jpg'
    assert inputs.last_read['bracket_started_at'] <= result['observed_at'] <= inputs.last_read['bracket_ended_at']


@pytest.mark.parametrize('changes', [
    {'mode': 'DISABLED'}, {'mode': 'FAULT'}, {'mode': 'STOPPING'}, {'feedback_available': False},
    {'dataset': {'robot_id': 'yam-1'}}, {'left_gripper': None}, {'joints': [0]*11},
    {'adapter_fault': 'fault'}, {'backend': 'simulated'},
])
def test_display_cache_fault_or_wrong_robot_never_become_model_state(changes):
    value = status(); value.update(changes)
    with pytest.raises((ValueError, RuntimeError)):
        source(value)()


def test_active_session_telemetry_is_read_without_queue_or_ownership_changes():
    value = status()
    value.update(mode='API_ACTIVE', api={'session_id': 'existing'},
                 auto_queue={'enabled': True, 'running': True})
    inputs = source(value)
    assert inputs()['left_gripper'] == .3
    assert inputs.last_read['existing_session_present'] is True
    assert value['api']['session_id'] == 'existing'
    assert value['auto_queue'] == {'enabled': True, 'running': True}


def test_nonlocal_inputs_rejected_before_connection():
    with pytest.raises(ValueError):
        LoopbackControllerInputs(robot_id='r', cameras=dict(left=6, top=12, right=18),
            operator_origin='https://example.com')


def test_slow_native_snapshot_is_not_retimestamped_as_fresh():
    with patch('remote_yam.controller_dream.time.monotonic', side_effect=[1., 2.1]):
        with pytest.raises(RuntimeError, match='stale'):
            source(status())()


class Policy:
    def __init__(self, **kwargs): self.kwargs = kwargs
    def build_trajectory(self, prompt, observation, first):
        return [dict(step_id=first, left_joints_deg=[1]*6, right_joints_deg=[2]*6,
            left_gripper=.3, right_gripper=.7)]
    def close_transport(self): self.closed = True


def bound():
    packets = []
    op = SimpleNamespace(lock=threading.RLock(), api_session_id='session', api_episode_id='episode',
        api_lease_id='lease', api_authorized=True, mode='API_ACTIVE', api_last_step=7,
        api_client=SimpleNamespace(jetson_id='robohouse'),
        _api_observation_locked=lambda: {}, api_handle_joint_trajectory=lambda p: packets.append(p) or ['native'])
    adapter = NativeControllerDream(op, robot_id='robohouse', credentials='unused', python='unused',
        directory='unused', adapter_factory=Policy)
    return op, adapter, packets


def test_native_submission_uses_existing_handler_current_lease_and_step_once():
    op, adapter, packets = bound()
    points = adapter.predict('hold')
    assert packets == []
    points[0]['left_joints_deg'][0] = 999
    assert adapter.submit() == ['native']
    assert packets[0]['waypoints'][0]['left_joints_deg'][0] == 1
    assert packets[0]['waypoints'][0]['step_id'] == 8
    assert packets[0]['lease_id'] == 'lease'
    assert packets[0]['cadence_hz'] == 10
    with pytest.raises(RuntimeError): adapter.submit()


def test_dispatch_does_not_hold_operator_lock_before_native_hardware_lock():
    op, adapter, packets = bound()
    acquired = []
    def dispatch(payload):
        def other_thread():
            with op.lock:
                acquired.append(True)
        thread = threading.Thread(target=other_thread)
        thread.start()
        thread.join(.5)
        assert not thread.is_alive(), 'Native handler was called with operator lock held'
    adapter.dispatch = dispatch
    adapter.predict('hold')
    adapter.submit()
    assert acquired == [True]


@pytest.mark.parametrize('change', ['lease', 'authorization', 'stop'])
def test_stop_or_ownership_change_discards_prediction(change):
    op, adapter, packets = bound()
    adapter.predict('hold')
    if change == 'lease': op.api_lease_id = 'replacement'
    elif change == 'authorization': op.api_authorized = False
    else: op.mode = 'STOPPED'
    assert adapter.adapter.cancelled()
    with pytest.raises(RuntimeError): adapter.submit()
    assert packets == []


def test_change_during_inference_is_discarded():
    op, adapter, packets = bound()
    original = adapter.adapter.build_trajectory
    def predict(*args):
        result = original(*args)
        op.api_lease_id = 'replacement'
        return result
    adapter.adapter.build_trajectory = predict
    with pytest.raises(RuntimeError): adapter.predict('hold')
    with pytest.raises(RuntimeError): adapter.submit()
    assert packets == []
