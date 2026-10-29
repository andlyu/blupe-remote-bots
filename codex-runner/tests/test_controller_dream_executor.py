import threading
import time
from types import SimpleNamespace

import pytest

from remote_yam.controller_dream import NativeControllerDream
from remote_yam.controller_dream_executor import DreamControllerExecutor
from remote_yam.controller_executor import ROBOHOUSE


class Pool:
    def __init__(self, *args): pass
    def prime(self): pass
    def status(self): return {'ready': True}
    def factory(self, *args): raise AssertionError('No real SDK in unit tests')


class Adapter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.completed = self.failed = self.adjusted = 0
        self._max_commands = 1
    def configure_run_duration(self, seconds): pass
    def build_trajectory(self, prompt, obs, first):
        return [dict(step_id=first, left_joints_deg=[1.]*6, right_joints_deg=[2.]*6,
                     left_gripper=.3, right_gripper=.7)]
    def trajectory_completed(self, obs, count): self.completed += count
    def trajectory_failed(self, *args, **kwargs): self.failed += 1
    def trajectory_adjusted(self, details): self.adjusted += 1
    def close_transport(self): pass


def setup(native_handler=None, adapter_factory=Adapter):
    sent, submitted, adapters = [], [], []
    context = dict(session_id='session', episode_id='episode', lease_id='lease')
    def observation():
        return dict(context, type='observation', step_id=0, homed=True, settled=True,
                    observed_at=time.time(), left_joints_deg=[0.]*6, right_joints_deg=[0.]*6)
    op = SimpleNamespace(lock=threading.RLock(), api_session_id='session', api_episode_id='episode',
        api_lease_id='lease', api_authorized=True, mode='API_ACTIVE', api_last_step=-1,
        api_client=SimpleNamespace(jetson_id=ROBOHOUSE, send=sent.append),
        _api_observation_locked=observation)
    def stop(payload):
        op.api_authorized = False
        executor.cancel()
    op.api_handle_stop = stop
    def execute(payload):
        submitted.append(payload)
        if native_handler:
            return native_handler(op, payload)
        common = dict(context, trajectory_id=payload['trajectory_id'], reported_at=time.time())
        op.api_client.send(dict(common, type='trajectory_result', status='accepted'))
        for point in payload['waypoints']:
            op.api_client.send(dict(common, type='trajectory_progress', step_id=point['step_id'], executed_at=time.time()))
        final = dict(observation(), **{k:v for k,v in payload['waypoints'][-1].items() if k != 'step_id'})
        final['step_id'] = payload['waypoints'][-1]['step_id'] + 1
        op.api_client.send(final)
        op.api_last_step = final['step_id'] - 1
        op.api_client.send(dict(common, type='trajectory_result', status='completed', step_id=op.api_last_step))
        return []
    op.api_handle_joint_trajectory = execute
    def native(*args, **kwargs):
        instance = NativeControllerDream(*args, **kwargs, adapter_factory=adapter_factory)
        adapters.append(instance.adapter)
        return instance
    executor = DreamControllerExecutor(op, robot_id=ROBOHOUSE, credentials='unused', python='unused',
        directory='unused', pool_factory=Pool, native_factory=native)
    executor.prepare(dict(context, task='move block', run_duration_s=120))
    request = dict(context, executor='dream_one', operation='start', payload={}, expires_at=time.time()+120)
    return op, executor, request, submitted, sent, adapters


def finish(executor):
    executor.thread.join(2)
    assert not executor.thread.is_alive()
    return executor.status()['state']


def test_full_native_loop_consumes_only_own_receipts_and_preserves_observations():
    op, executor, request, submitted, sent, adapters = setup()
    executor.request(request)
    assert finish(executor) == 'completed'
    assert len(submitted) == 1
    assert submitted[0]['lease_id'] == request['lease_id']
    assert [p['type'] for p in sent] == ['observation']
    assert adapters[0].completed == 1
    # New request ID for this lease cannot restart a completed policy.
    executor.request(request)
    assert len(submitted) == 1
    op.api_client.send(dict(type='trajectory_result', trajectory_id='other', **{
        k:request[k] for k in ('session_id', 'episode_id', 'lease_id')}))
    assert sent[-1]['trajectory_id'] == 'other'


def test_predict_operation_never_reaches_native_motion_handler():
    op, executor, request, submitted, sent, adapters = setup()
    executor.request(dict(request, operation='predict'))
    assert finish(executor) == 'completed'
    assert not submitted and not sent
    assert executor.status()['predictions'] == 1
    assert executor.status()['predicted_waypoints'] == 1
    assert executor.status()['packets'] == 0


@pytest.mark.parametrize('change', [dict(lease_id='wrong'), dict(expires_at=0),
    dict(payload={'prompt':'override'}), dict(operation='shell')])
def test_invalid_request_cannot_start_worker_or_motion(change):
    op, executor, request, submitted, sent, adapters = setup()
    with pytest.raises(ValueError): executor.request(dict(request, **change))
    assert not submitted and not adapters


def test_stop_returns_without_waiting_for_prediction_and_discards_late_packet():
    entered, release = threading.Event(), threading.Event()
    class Slow(Adapter):
        def build_trajectory(self, *args):
            entered.set()
            release.wait(2)
            return super().build_trajectory(*args)
    op, executor, request, submitted, sent, adapters = setup(adapter_factory=Slow)
    executor.request(request)
    assert entered.wait(1)
    executor.cancel()
    assert executor.thread.is_alive()  # Stop did not join the stalled prediction.
    op.api_authorized = False
    release.set()
    assert finish(executor) == 'cancelled'
    assert not submitted


def test_lease_change_discards_prediction_before_native_submission():
    class NewLease(Adapter):
        def build_trajectory(self, *args):
            op.api_lease_id = 'new-lease'
            return super().build_trajectory(*args)
    op, executor, request, submitted, sent, adapters = setup(adapter_factory=NewLease)
    executor.request(request)
    assert finish(executor) == 'cancelled'
    assert not submitted


def test_completed_without_all_progress_fails_closed_and_stops_native_lease():
    def incomplete(op, payload):
        return [dict(payload, type='trajectory_result', status='completed', step_id=0)]
    op, executor, request, submitted, sent, adapters = setup(native_handler=incomplete)
    executor.request(request)
    assert finish(executor) == 'failed'
    assert not op.api_authorized and adapters[0].completed == 0
    assert sent[-1]['type'] == 'safety_abort'
    assert sent[-1]['message'] == 'Controller Dream execution failed'


def test_failed_notification_cannot_prevent_local_native_stop():
    def incomplete(op, payload):
        return [dict(payload, type='trajectory_result', status='completed', step_id=0)]
    op, executor, request, submitted, sent, adapters = setup(native_handler=incomplete)
    executor._send = lambda payload: (_ for _ in ()).throw(ConnectionError('private transport detail'))
    executor.request(request)
    assert finish(executor) == 'failed'
    assert not op.api_authorized


def test_premature_final_observation_is_not_accepted_after_later_progress():
    def out_of_order(op, payload):
        context = {k:payload[k] for k in ('session_id','episode_id','lease_id','trajectory_id')}
        op.api_client.send(dict(context, type='trajectory_result', status='accepted'))
        op.api_client.send(dict(context, type='observation', step_id=1, settled=True,
            left_joints_deg=[1.]*6, right_joints_deg=[2.]*6))
        op.api_client.send(dict(context, type='trajectory_progress', step_id=0))
        op.api_client.send(dict(context, type='trajectory_result', status='completed', step_id=0))
        return []
    op, executor, request, submitted, sent, adapters = setup(native_handler=out_of_order)
    executor.request(request)
    assert finish(executor) == 'failed'
    assert adapters[0].completed == 0


def test_native_workspace_hold_requires_evidence_and_fresh_prediction():
    def held(op, payload):
        op.api_last_step = payload['waypoints'][-1]['step_id']
        return [dict(payload, type='trajectory_result', status='rejected',
            code='left_tip_outside_workspace', details=dict(recoverable=True,
                workspace_recovery='held', hold='measured_position', next_step_id=1, executed_waypoints=0))]
    op, executor, request, submitted, sent, adapters = setup(native_handler=held)
    executor.request(request)
    assert finish(executor) == 'completed'
    assert adapters[0].failed == 1 and adapters[0].completed == 0
