import io
import math
import shutil
import threading
import copy
from unittest.mock import patch

import pytest
from PIL import Image

import playground
from remote_yam.cameras import CameraFrame
from remote_yam.session import MockSessionAPI
from remote_yam.controller import RunnerController
from remote_yam.yam_runpod_policy import YAMRunpodAdapter, MODELS, GRIPPER_UNITS


def fixture(provider='dreamzero'):
    image = io.BytesIO()
    Image.new('RGB', (640, 360)).save(image, format='JPEG')
    class Cameras:
        def capture_for_policy(self, *args, **kwargs):
            return [CameraFrame(name, image.getvalue(), 0) for name in ('left', 'top', 'right')]
    policy = YAMRunpodAdapter('private-service-secret', provider=provider,
        endpoint='https://fixture.api.runpod.ai', camera_source=Cameras(), robot_id='yam-1')
    policy._ready.set()
    observation = dict(jetson_id='yam-1', left_joints_deg=[10] * 6,
        right_joints_deg=[-10] * 6, left_gripper=.2, right_gripper=.8)
    rows = [[.001 * (i + 1)] * 6 + [.2] + [-.001 * (i + 1)] * 6 + [.8]
            for i in range(policy.spec['num_actions'])]
    result = dict(robot_id='yam-1', model=policy.model, revision=policy.spec['revision'],
        action_units='radians', gripper_units=GRIPPER_UNITS, device='cuda:0', actions=rows)
    return policy, observation, result


@pytest.mark.parametrize('provider,points,duration', [('dreamzero', 8, .8), ('molmoact2', 10, 1)])
def test_exact_checkpoint_joint_order_and_native_duration(provider, points, duration):
    policy, observation, result = fixture(provider)
    if provider == 'molmoact2':
        # A nearby chunk keeps its native duration; large moves are tested below.
        for row in result['actions']:
            for i in range(6):
                row[i] += math.radians(10)
                row[i + 7] -= math.radians(10)
    seen = []
    policy._json = lambda path, payload: seen.append(payload) or result
    trajectory = policy.build_trajectory('Pick up the block.', observation, 20)
    assert len(trajectory) == points and len(trajectory) / 10 == duration
    assert seen[0]['robot_id'] == 'yam-1'
    assert seen[0]['state'] == pytest.approx([math.radians(10)] * 6 + [.2] + [math.radians(-10)] * 6 + [.8])
    assert set(seen[0]['images']) == {'top', 'left', 'right'}
    assert seen[0]['gripper_units'] == GRIPPER_UNITS
    for i, (point, row) in enumerate(zip(trajectory, result['actions'][2::3])):
        assert point['step_id'] == 20 + i
        assert point['left_joints_deg'] == pytest.approx([math.degrees(x) for x in row[:6]])
        assert point['right_joints_deg'] == pytest.approx([math.degrees(x) for x in row[7:13]])
        assert (point['left_gripper'], point['right_gripper']) == (.2, .8)
    assert 'private-service-secret' not in str(policy.public_config())
    assert 'fixture.api.runpod.ai' not in str(policy.public_config())


@pytest.mark.parametrize('robot', ['robot-ba8413962083809c', 'robohouse', '', None])
def test_other_or_missing_robot_identity_never_reaches_inference(robot):
    policy, observation, _ = fixture()
    policy._json = lambda *args: pytest.fail('Wrong robot must not reach the model')
    observation['jetson_id'] = robot
    with pytest.raises(ValueError, match='YAM1'):
        policy.build_trajectory('Pick up the block.', observation, 0)
    with pytest.raises(ValueError, match='YAM1'):
        YAMRunpodAdapter('secret', provider='dreamzero', endpoint='https://fixture.api.runpod.ai',
            camera_source=None, robot_id=robot)


@pytest.mark.parametrize('change', [dict(robot_id='robohouse'), dict(revision='wrong'),
    dict(model=MODELS['molmoact2']['model']), dict(action_units='degrees'),
    dict(gripper_units='radians'), dict(device='cpu')])
def test_wrong_identity_units_or_cpu_response_rejects_entire_chunk(change):
    policy, observation, result = fixture()
    policy._json = lambda *args: {**result, **change}
    with pytest.raises(ValueError, match='chunk'):
        policy.build_trajectory('Pick up the block.', observation, 0)


@pytest.mark.parametrize('index,value', [(6, -.01), (13, 1.01), (0, float('nan')), (0, True)])
def test_invalid_unsampled_molmoact_row_is_rejected_without_clamping(index, value):
    policy, observation, result = fixture('molmoact2')
    result['actions'][0][index] = value
    policy._json = lambda *args: result
    with pytest.raises(ValueError, match='chunk'):
        policy.build_trajectory('Pick up the block.', observation, 0)


def test_dreamzero_continuous_grippers_map_to_endpoints_without_changing_joints_or_raw_result():
    policy, observation, result = fixture()
    result['actions'][2][6] = -.03
    result['actions'][2][13] = 1.054142890846263
    events = []
    policy.interaction_sink = lambda kind, message, **details: events.append((kind, details))
    policy._json = lambda *args: result
    points = policy.build_trajectory('Put the orange block into the box.', observation, 0)
    assert points[0]['left_gripper'] == 0
    assert points[0]['right_gripper'] == 1
    assert points[0]['left_joints_deg'] == pytest.approx([math.degrees(.003)] * 6)
    assert result['actions'][2][6] == -.03
    assert result['actions'][2][13] == 1.054142890846263
    response = next(details for kind, details in events if kind == 'model_response')
    assert response['gripper_values_clipped'] == 2
    assert response['raw_gripper_max'] == 1.054142890846263
    assert any(kind == 'model_timing' for kind, _ in events)


@pytest.mark.parametrize('index,value', [(0, float('nan')), (6, float('inf')), (13, True)])
def test_dreamzero_invalid_unsampled_values_still_reject_whole_chunk(index, value):
    policy, observation, result = fixture()
    result['actions'][0][index] = value
    policy._json = lambda *args: result
    with pytest.raises(ValueError, match='nonfinite_or_nonnumeric_action'):
        policy.build_trajectory('Pick up the block.', observation, 0)


@pytest.mark.parametrize('name', ['dreamzero', 'molmoact2'])
@pytest.mark.parametrize('stop_before_ready', [False, True])
def test_cold_gpu_must_be_ready_before_any_robot_session(name, stop_before_ready):
    policy, _, result = fixture(name)
    policy._ready.clear()
    entered, release, admitted = threading.Event(), threading.Event(), threading.Event()
    health = dict(result, ok=True, cuda_available=True, action_dim=14,
        num_actions=policy.spec['num_actions'], norm_tag=policy.spec['norm_tag'])
    def response(path):
        assert path == '/health'
        entered.set()
        assert release.wait(3)
        return health
    policy._json = response
    class Session(MockSessionAPI):
        def create_session(self, *args, **kwargs):
            assert policy._ready.is_set()
            assert kwargs['run_duration_s'] == 120
            admitted.set()
            return super().create_session(*args, **kwargs)
    api = Session(auto_activate=False)
    controller = RunnerController(api)
    try:
        state = controller.join_and_run(policy, 'Pick up the block.', run_duration_s=120)
        assert state['status'] == 'preparing'
        assert entered.wait(2)
        assert not admitted.is_set() and not api._sessions
        assert controller.status()['run_started_at'] is None
        if stop_before_ready:
            controller.stop()
        release.set()
        if stop_before_ready:
            controller._worker.join(2)
            assert not admitted.is_set() and not api._sessions
        else:
            assert admitted.wait(2)
        assert not api.action_log
    finally:
        release.set()
        controller.stop()
        if policy._thread:
            policy._thread.join(2)


def test_wrong_horizon_budget_overflow_and_late_stop_never_return_commands():
    policy, observation, result = fixture()
    policy._json = lambda *args: {**result, 'actions': result['actions'] + result['actions'][:6]}
    with pytest.raises(ValueError, match='chunk'):
        policy.build_trajectory('Pick up the block.', observation, 0)
    policy._json = lambda *args: result
    with pytest.raises(ValueError, match='budget'):
        policy.build_trajectory('Pick up the block.', observation, 2993)
    def late(*args):
        policy.cancelled = lambda: True
        return result
    policy._json = late
    with pytest.raises(RuntimeError, match='cancelled'):
        policy.build_trajectory('Pick up the block.', observation, 0)


def test_wrong_health_identity_cannot_finish_preparation():
    policy, _, result = fixture()
    policy._ready.clear()
    policy._json = lambda path: {**result, 'ok': True, 'cuda_available': True,
        'action_dim': 14, 'num_actions': 30, 'norm_tag': policy.spec['norm_tag']}
    with patch('remote_yam.yam_runpod_policy.time.monotonic', side_effect=[0, 1201]):
        policy._keep_ready(lambda: False)
    assert not policy._ready.is_set() and policy._warm_state == 'failed'


@pytest.mark.parametrize('robot,hardware,enabled', [
    ('yam-1', 'yam', True), ('robot-ba8413962083809c', 'yam', False),
    ('robohouse', 'yam', False), ('yam-1', 'custom', False)])
def test_hosted_policy_catalog_is_only_for_yam1(robot, hardware, enabled, tmp_path):
    key = tmp_path / 'key'
    key.write_text('private-service-secret')
    app = playground.HostedRunner(public_origin='https://robot.example', session_api='https://session.example',
        camera_origin='https://session.example', robot_id=robot, hardware=hardware,
        runpod_key_file=str(key), runpod_config={'dreamzero': {'endpoint': 'https://fixture.api.runpod.ai'}},
        api_factory=lambda: MockSessionAPI(auto_activate=False))
    _, visitor = app.new_visitor()
    payload = dict(provider='dreamzero', model=MODELS['dreamzero']['model'], prompt='Pick up the block.')
    try:
        assert ('dreamzero' in app.runpod_providers) is enabled
        assert ('dreamzero' in app.extra_providers) is enabled
        if enabled:
            with pytest.raises(playground.RequestError, match='checkpoint'):
                app.launch(visitor, {**payload, 'model': MODELS['molmoact2']['model']})
            with patch.object(YAMRunpodAdapter, 'start_preparation'):
                assert app.launch(visitor, payload)['ok']
            assert not visitor.controller._session_api.action_log
        else:
            with pytest.raises(playground.RequestError):
                app.launch(visitor, payload)
    finally:
        visitor.controller.stop()
        visitor.close()
        shutil.rmtree(app.root, ignore_errors=True)


@pytest.mark.parametrize('internal', [False, True])
@pytest.mark.parametrize('joint', [0, 5, 7, 12])
def test_molmoact_large_transitions_are_paced_without_losing_targets(internal, joint):
    policy, observation, result = fixture('molmoact2')
    observation.update(left_joints_deg=[0.] * 6, right_joints_deg=[0.] * 6)
    rows = [[0.] * 6 + [.2] + [0.] * 6 + [.8] for _ in range(30)]
    for row in rows[15 if internal else 0:]:
        row[joint] = .296875  # Exact largest jump in the recorded failed packet.
        row[6], row[13] = .8, .2
    result['actions'] = rows
    original = copy.deepcopy(rows)
    policy._json = lambda *args: result
    points = policy.build_trajectory('Put the orange block into the bin.', observation, 20)
    previous = [0.] * 6 + [.2] + [0.] * 6 + [.8]
    reconstructed = []
    for point in points:
        row = ([math.radians(v) for v in point['left_joints_deg']] + [point['left_gripper']]
               + [math.radians(v) for v in point['right_joints_deg']] + [point['right_gripper']])
        assert max(abs(row[i] - previous[i]) for i in (*range(6), *range(7, 13))) <= .03 + 1e-12
        assert 0 <= row[6] <= 1 and 0 <= row[13] <= 1
        reconstructed.append(row)
        previous = row
    cursor = 0
    for target in rows[2::3]:
        while reconstructed[cursor] != pytest.approx(target):
            cursor += 1
        cursor += 1
    assert points[-1]['step_id'] == 20 + len(points) - 1
    assert len(points) > 10
    assert result['actions'] == original


def test_molmoact_pacing_rejects_whole_chunk_when_expansion_exceeds_budget():
    policy, observation, result = fixture('molmoact2')
    observation.update(left_joints_deg=[0.] * 6, right_joints_deg=[0.] * 6)
    policy._json = lambda *args: result
    result['actions'] = [[.3] * 6 + [.2] + [0.] * 6 + [.8] for _ in range(30)]
    with pytest.raises(ValueError, match='budget'):
        policy.build_trajectory('Put the block into the bin.', observation, 2990)


def test_molmoact_pacing_starts_from_leased_feedback_after_inference():
    policy, observation, result = fixture('molmoact2')
    observation.update(left_joints_deg=[0.] * 6, right_joints_deg=[0.] * 6)
    fresh = dict(observation, left_joints_deg=[20.] * 6)
    seen = []
    policy._json = lambda path, payload: seen.append(payload) or result
    policy.refresh_observation = lambda: fresh
    points = policy.build_trajectory('Put the block into the bin.', observation, 0)
    assert seen[0]['state'][:6] == [0.] * 6
    first = points[0]['left_joints_deg']
    assert max(abs(math.radians(v - 20)) for v in first) <= .03 + 1e-12


@pytest.mark.parametrize('stop', [False, True])
def test_molmoact_pacing_does_not_hide_lease_failure_or_stop(stop):
    policy, observation, result = fixture('molmoact2')
    policy._json = lambda *args: result
    def refresh():
        if stop:
            policy.cancelled = lambda: True
            return observation
        raise RuntimeError('Session changed before model retry')
    policy.refresh_observation = refresh
    with pytest.raises(RuntimeError, match='cancelled' if stop else 'Session changed'):
        policy.build_trajectory('Put the block into the bin.', observation, 0)
