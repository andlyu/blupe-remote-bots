import copy
import json
import math
import time
from unittest.mock import Mock

import pytest

from remote_yam.controller import RunnerController
from remote_yam.providers import PolicyComplete, RaiseLowerSimulationAdapter, RepeatingRaiseLowerAdapter
from remote_yam.robocurve_policy import RoboCurveResponsesAdapter
from remote_yam.session import MockSessionAPI
from test_dream_policy import adapter, observation
from test_trajectory_transport import TinyTrajectoryProvider
from test_robocurve_policy import Cameras, observation as tool_observation, response


def details(state='adjusted', progress=0):
    result = dict(workspace_recovery=state, boundaries=['left.z_lower'], changed_waypoints=2,
        left_joints_deg=[1.]*6, right_joints_deg=[2.]*6, left_gripper=.3, right_gripper=.7)
    if state == 'held':
        result.update(recoverable=True, hold='measured_position', executed_waypoints=progress, next_step_id=3)
    return result


def controller(state='dispatched', progress=0):
    api = MockSessionAPI()
    runner = RunnerController(api)
    runner._provider = Mock()
    runner._joint_counts = (6, 6)
    runner._session_id, runner._episode_id, runner._lease_id = 'session', 'episode', 'lease'
    runner._command_step_id, runner._status = 3, 'running'
    runner._trajectory = dict(trajectory_id='trajectory', state=state, progress_count=progress,
        first_step_id=0, last_step_id=2, waypoint_count=3, last_progress_step_id=progress-1 if progress else None,
        final_observation_received=False, final_target=dict(step_id=2, left_joints_deg=[9.]*6,
        right_joints_deg=[9.]*6, left_gripper=.5, right_gripper=.5), path_segments=[{'left_displacement_m':1.}]*3)
    return runner


def result(status='accepted', recovery=None, **kwargs):
    return dict(trajectory_id='trajectory', status=status, reported_at=time.time(),
        episode_id='episode', lease_id='lease', details=recovery or {}, **kwargs)


def tool_provider():
    provider = RoboCurveResponsesAdapter('fixture-key', 'fixture-model', 'https://example.invalid',
        camera_source=Cameras())
    provider._pending = dict(call_id='call_1', waypoint_count=3, first_step_id=0, last_step_id=2)
    return provider


def test_adjusted_target_used_for_final_feedback_and_pending_callback():
    runner = controller()
    replacement = details()
    runner._trajectory_result(result(recovery=replacement))
    assert runner._trajectory['final_target']['left_joints_deg'] == replacement['left_joints_deg']
    assert runner._trajectory['path_segments'] == []
    runner._provider.trajectory_adjusted.assert_called_once_with(replacement)
    provider = TinyTrajectoryProvider()
    provider.validate_trajectory_final = None
    runner._trajectory['progress_count'] = 3
    runner._trajectory_final_observation(provider, dict(replacement, settled=True), 3)
    assert 'final_position_mismatch' not in runner._trajectory
    # Identical acceptance replay cannot duplicate callback; changed metadata fails.
    runner._trajectory_result(result(recovery=replacement))
    runner._provider.trajectory_adjusted.assert_called_once()
    with pytest.raises(RuntimeError, match='changed its workspace replacement'):
        runner._trajectory_result(result(recovery=dict(replacement, left_joints_deg=[3.]*6)))


@pytest.mark.parametrize('bad', [dict(left_joints_deg=[math.nan]*6), dict(left_joints_deg=[1.]*5),
    dict(right_gripper=2), dict(changed_waypoints=0), dict(changed_waypoints=True)])
def test_malformed_replacement_fails_closed(bad):
    runner = controller()
    with pytest.raises(RuntimeError):
        runner._trajectory_result(result(recovery=dict(details(), **bad)))


@pytest.mark.parametrize('status,progress', [('rejected', 0), ('aborted', 1), ('aborted', 3)])
def test_workspace_hold_continues_without_committing_or_replaying(status, progress):
    runner = controller('accepted' if status == 'aborted' else 'dispatched', progress)
    payload = result(status, details('held', progress), code='left_tip_outside_workspace',
        message='Boundary reached; held', step_id=min(progress, 2) if status == 'aborted' else None)
    runner._trajectory_result(payload)
    assert runner._trajectory is None
    assert runner._status == 'running' and runner._command_step_id == 3
    runner._provider.trajectory_completed.assert_not_called()
    runner._provider.trajectory_failed.assert_called_once()
    assert runner._workspace_replan_not_before > time.monotonic()
    runner._trajectory_result(dict(payload, replayed=True))
    runner._provider.trajectory_failed.assert_called_once()


@pytest.mark.parametrize('bad', [dict(recoverable=False), dict(next_step_id=2), dict(hold='unknown'),
    dict(executed_waypoints=1), dict(workspace_recovery='adjusted')])
def test_hold_without_consistent_evidence_is_terminal(bad):
    runner = controller()
    with pytest.raises(RuntimeError):
        runner._trajectory_result(result('rejected', dict(details('held'), **bad),
            code='left_tip_outside_workspace'))
    assert runner._trajectory is not None


def test_real_fault_cannot_opt_into_workspace_recovery():
    runner = controller()
    with pytest.raises(RuntimeError, match='physical_execution_failure'):
        runner._trajectory_result(result('aborted', details('held'), code='physical_execution_failure'))


@pytest.mark.parametrize('status,progress', [('rejected', 0), ('aborted', 1), ('aborted', 3)])
def test_tool_provider_returns_actual_held_prefix_and_releases_pending(status, progress):
    runner = controller('accepted' if status == 'aborted' else 'dispatched', progress)
    provider = runner._provider = tool_provider()
    feedback = details('held', progress)
    runner._trajectory_result(result(status, feedback, code='left_tip_outside_workspace',
        step_id=min(progress, 2) if status == 'aborted' else None))
    output = json.loads(provider._history[-1]['output'])
    assert output['ok'] is False and output['status'] == 'not_reached'
    assert output['steps'] == progress and output['feedback'] == feedback
    assert provider._pending is None and runner._trajectory is None
    assert 'remaining actions were discarded' in output['instruction']


@pytest.mark.parametrize('code,progress,bad', [
    ('left_tip_outside_workspace', 0, {'recoverable':False}),
    ('right_tip_outside_workspace', 1, {'hold':'unknown'}),
    ('left_tip_outside_workspace', 1, {'workspace_recovery':'adjusted'}),
    ('left_tip_outside_workspace', 1, {'executed_waypoints':0}),
    ('left_tip_outside_workspace', 1, {'executed_waypoints':True}),
    ('left_tip_outside_workspace', 1, {'next_step_id':2}),
    ('left_tip_outside_workspace', -1, {}),
    ('left_tip_outside_workspace', 4, {}),
    ('left_tip_outside_workspace', True, {}),
    ('physical_execution_failure', 3, {}),
    ('joint_settle_timeout', 1, {}),
    ('final_position_mismatch', 1, {}),
])
def test_tool_provider_rejects_unverified_workspace_or_incomplete_settle_failure(code, progress, bad):
    provider = tool_provider()
    with pytest.raises(RuntimeError):
        provider.trajectory_failed(code, 'fixture failure', progress,
            feedback=dict(details('held', progress), **bad))
    assert provider._pending is not None and provider._history == []


@pytest.mark.parametrize('code', ['joint_settle_timeout', 'final_position_mismatch'])
def test_tool_provider_preserves_complete_settle_failure_feedback(code):
    provider = tool_provider()
    provider.trajectory_failed(code, 'target missed', 3)
    assert json.loads(provider._history[-1]['output'])['code'] == code
    assert provider._pending is None


def test_tool_adjustment_reports_replacement_only_after_measured_completion():
    runner = controller()
    provider = runner._provider = tool_provider()
    replacement = dict(details(), orientation_relaxed=True, boundary_limits=['left.z_lower=.03m'])
    runner._trajectory_result(result(recovery=replacement))
    assert provider._history == []
    assert runner._workspace_feedback == replacement
    assert provider._pending['workspace_recovery'] == replacement
    assert provider._pending['workspace_recovery'] is not replacement
    runner._trajectory['progress_count'] = 3
    measured = dict(replacement, step_id=3, settled=True)
    runner._trajectory_final_observation(provider, measured, 3)
    runner._trajectory['final_payload'] = measured
    runner._observation = Mock()
    runner._trajectory_result(result('completed', step_id=2))
    output = json.loads(provider._history[-1]['output'])
    assert output['status'] == 'completed' and output['feedback'] == replacement
    assert output['feedback']['orientation_relaxed'] is True
    assert 'original requested motion was changed' in output['instruction']
    assert provider._pending is None
    runner._observation.assert_called_once_with({}, measured)


def test_tool_provider_chooses_again_from_fresh_input_after_workspace_hold():
    provider = tool_provider()
    provider._pending = None
    provider._post_json = Mock(side_effect=[
        response('move_to', {'targets':{'left_z':.195}, 'note':'Raise slightly.'}),
        response('give_up', {'reason':'Boundary prevents this approach.', 'hindsight':'Choose another approach.'}, 'call_2')])
    before = tool_observation()
    points = provider.build_trajectory('move apple', before, 0)
    feedback = dict(details('held'), next_step_id=len(points))
    provider.trajectory_failed('left_tip_outside_workspace', 'Measured hold', 0, feedback=feedback)
    after = dict(before, step_id=len(points))
    with pytest.raises(PolicyComplete):
        provider.build_trajectory('move apple', after, len(points))
    assert provider._post_json.call_count == 2 and provider._camera_source.calls == 2
    next_input = provider._post_json.call_args.args[0]['input']
    failed = next(item for item in next_input if item.get('type') == 'function_call_output')
    assert json.loads(failed['output'])['feedback'] == feedback
    assert provider._pending is None


@pytest.mark.parametrize('policy', [RaiseLowerSimulationAdapter, RepeatingRaiseLowerAdapter])
def test_cached_deterministic_provider_cannot_replay_workspace_held_packet(policy):
    runner = controller()
    runner._provider = policy()
    with pytest.raises(RuntimeError, match='cached packet will not be replayed'):
        runner._trajectory_result(result('rejected', details('held'), code='left_tip_outside_workspace'))
    assert runner._trajectory is not None
    assert runner._workspace_feedback is None


def test_whole_run_continues_from_measured_hold_without_replaying_rejected_packet():
    class BoundaryOnceSession(MockSessionAPI):
        injected = False
        held_id = None
        def submit_trajectory(self, *args):
            if not self.injected:
                self.hold = args[-1][0]
            return super().submit_trajectory(*args)
        def _event(self, record, kind, payload):
            if kind == 'trajectory_result' and payload.get('status') == 'accepted' and not self.injected:
                self.injected = True
                self.held_id = payload['trajectory_id']
                super()._event(record, kind, dict(payload, status='rejected',
                    code='left_tip_outside_workspace', details=details('held')))
                return
            if self.held_id:
                if kind == 'trajectory_progress':
                    return
                if kind == 'trajectory_result' and payload.get('status') == 'completed':
                    self.held_id = None
                    return
                if kind == 'observation':
                    payload = dict(payload, **{key:self.hold[key] for key in
                        ('left_joints_deg', 'right_joints_deg', 'left_gripper', 'right_gripper')})
            super()._event(record, kind, payload)
    provider = TinyTrajectoryProvider()
    failures = []
    provider.trajectory_failed = lambda *args, **kw: failures.append((args, kw))
    api = BoundaryOnceSession()
    runner = RunnerController(api)
    runner.update_monitor_observation(api.get_robot_observation('yam-1'))
    runner.join(provider, 'Continue after boundary hold')
    runner._run_loop(None)
    status = runner.status()
    assert status['error'] is None
    assert status['status'] == 'stopped'
    assert len(failures) == 1
    assert [packet['waypoints'][0]['step_id'] for packet in api.trajectory_log] == [0, 3]
    assert runner._run_metrics['confirmed_waypoints'] == 3
    assert runner._run_metrics['accepted_packets'] == 1


@pytest.mark.parametrize('status,progress', [('rejected', 0), ('aborted', 1), ('aborted', 3)])
def test_finished_hold_reconnect_consumes_failure_before_observation(status, progress):
    runner = controller()
    failed = result(status, details('held', progress), code='left_tip_outside_workspace',
        step_id=min(progress, 2) if status == 'aborted' else None)
    accepted = [] if status == 'rejected' else [result()]
    runner._session_api.get_episode_trace = lambda session: dict(trajectory_results=accepted+[failed],
        trajectory_progress=[dict(trajectory_id='trajectory', episode_id='episode', lease_id='lease',
            step_id=step, executed_at=time.time()) for step in range(progress)])
    runner._recover_finished_trajectory()
    assert runner._trajectory is None
    runner._trajectory_result(dict(failed, replayed=True))
    runner._provider.trajectory_failed.assert_called_once()


def test_active_reconnect_restores_accepted_replacement_from_trace():
    runner = controller()
    runner._session_api.get_episode_trace = lambda session: dict(trajectory_results=[result(recovery=details())])
    runner._recover_trajectory(dict(trajectory_id='trajectory', state='accepted', first_step_id=0,
        last_step_id=2, waypoint_count=3, progress_count=2, last_progress_step_id=1,
        final_observation_received=False))
    assert runner._trajectory['final_target']['left_joints_deg'] == [1.]*6
    runner._provider.trajectory_adjusted.assert_called_once()


def test_finished_reconnect_restores_replacement_before_final_observation():
    runner = controller()
    runner._session_api.get_episode_trace = lambda session: dict(
        trajectory_results=[result(recovery=details()), result('completed')],
        trajectory_progress=[dict(trajectory_id='trajectory', episode_id='episode', lease_id='lease',
            step_id=step, executed_at=time.time()) for step in range(3)])
    runner._recover_finished_trajectory()
    assert runner._trajectory['final_target']['left_joints_deg'] == [1.]*6
    assert runner._trajectory['progress_count'] == 3


def test_dream_adjustment_commits_only_corrected_target_after_completion(tmp_path):
    provider = adapter(tmp_path)
    provider._pending_commanded = {'nominal': 'must be discarded'}
    provider.trajectory_adjusted(details())
    assert provider._commanded is None
    provider.trajectory_completed(observation(), 3)
    assert provider._commanded['q_l_chunk'][:6] == pytest.approx([math.radians(1.)]*6)
    assert provider._workspace_reset_pending is True
    provider.close_transport()


@pytest.mark.parametrize('held', [False, True])
def test_dream_reset_clears_buffers_and_uses_fresh_ticks_and_boundary_with_steering(tmp_path, held):
    provider = adapter(tmp_path)
    try:
        points = provider.build_trajectory('poke apple', observation(), 0)
        first_predict = [kw for name, kw in provider._worker.calls if name == 'predict'][-1]
        if held:
            provider.trajectory_failed('left_tip_outside_workspace', 'held', 0, feedback=details('held'))
        else:
            provider.trajectory_adjusted(details())
            provider.trajectory_completed(observation(), len(points))
        assert provider._pending_commanded is None
        provider.steering.submit('Move upward before trying again', 'request_000000001')
        count = len(provider._worker.calls)
        provider.build_trajectory('poke apple', observation(), len(points))
        calls = provider._worker.calls[count:]
        assert calls[0][0] == 'reset'
        fresh = next(kw for name, kw in calls if name == 'predict')
        assert fresh['commanded'] is None
        assert min(t['timestamp'] for t in fresh['ticks']) > max(t['timestamp'] for t in first_predict['ticks'])
        assert 'left.z_lower' in fresh['ticks'][-1]['observation']['prompt']
        assert 'poke apple' in fresh['ticks'][-1]['observation']['prompt']
        assert 'Move upward before trying again' in fresh['ticks'][-1]['observation']['prompt']
    finally:
        provider.close_transport()


def test_dream_failed_sdk_reset_never_predicts_stale_actions(tmp_path):
    provider = adapter(tmp_path)
    try:
        provider.build_trajectory('poke apple', observation(), 0)
        provider.trajectory_failed('left_tip_outside_workspace', 'held', 0, feedback=details('held'))
        calls = len([1 for name, kw in provider._worker.calls if name == 'predict'])
        original = provider._worker.call
        provider._worker.call = lambda name, **kw: {'ok': False} if name == 'reset' else original(name, **kw)
        with pytest.raises(RuntimeError, match='could not reset'):
            provider.build_trajectory('poke apple', observation(), 24)
        assert len([1 for name, kw in provider._worker.calls if name == 'predict']) == calls
    finally:
        provider.close_transport()
