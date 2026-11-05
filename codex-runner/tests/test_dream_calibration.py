"""Offline selected-calibration geometry and original-encoder regressions."""
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
import pytest

from remote_yam.dream_calibration import binding_from_report, kinematic_description, ROBOHOUSE
from remote_yam.dream_policy import DreamAdapter, state_input, action_waypoints
from remote_yam.mujoco_ik import BimanualRelativeIK


def report():
    return json.loads((Path(__file__).parent / 'fixtures/dream_robohouse_calibration.json').read_text())


def axis_rotation(axis, angle):
    # Independent matrix exponential through MuJoCo's axis-angle primitive.
    quat, matrix = np.empty(4), np.empty(9)
    mujoco.mju_axisAngle2Quat(quat, np.asarray(axis, float), angle)
    mujoco.mju_quat2Mat(matrix, quat)
    return matrix.reshape(3, 3)


def urdf_fk(xml, q):
    root, transform = ET.fromstring(xml), np.eye(4)
    for name, angle in [(f'joint{i+1}', value) for i, value in enumerate(q)] + [('sdk_flange', 0.)]:
        joint = root.find(f"joint[@name='{name}']")
        origin = joint.find('origin')
        roll, pitch, yaw = map(float, origin.get('rpy').split())
        local = np.eye(4)
        local[:3, 3] = list(map(float, origin.get('xyz').split()))
        local[:3, :3] = axis_rotation([0,0,1], yaw) @ axis_rotation([0,1,0], pitch) @ axis_rotation([1,0,0], roll)
        transform = transform @ local
        if joint.get('type') != 'fixed':
            local = np.eye(4)
            local[:3, :3] = axis_rotation(list(map(float, joint.find('axis').get('xyz').split())), angle)
            transform = transform @ local
    transform[:3, 3] += transform[:3, :3] @ [0, 0, .1347]
    return transform


@pytest.mark.parametrize('q', [[0.]*6, [0.,.5,.5,-.35,0.,0.],
    [.2,1.,1.3,-.4,.5,-.8], [-.4,.8,1.8,.4,-.3,.9]])
def test_generated_sdk_geometry_matches_calibrated_controller(q):
    binding = binding_from_report(report(), ROBOHOUSE)
    description = kinematic_description(binding)
    calibrated = BimanualRelativeIK(base_spacing_m=binding['base_spacing_m'],
        joint_offsets_rad=binding['offsets_rad']['left'] + binding['offsets_rad']['right'])
    calibrated.data.qpos[:12] = q + q
    mujoco.mj_kinematics(calibrated.model, calibrated.data)
    for side, sign in [('left', 1), ('right', -1)]:
        body = calibrated.model.body(side + '_grasp').id
        expected = np.eye(4)
        expected[:3, 3] = calibrated.data.xpos[body] - [0, sign*binding['base_spacing_m']/2, 0]
        expected[:3, :3] = calibrated.data.xmat[body].reshape(3,3) @ axis_rotation([0,0,1], math.pi/2)
        actual = urdf_fk(description['urdfs'][side], q)
        np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=0)
        tree = ET.fromstring(description['urdfs'][side])
        for index in range(1, 7):
            actual_limits = tree.find(f"joint[@name='joint{index}']/limit")
            np.testing.assert_array_equal([float(actual_limits.get(k)) for k in ['lower','upper']],
                calibrated.model.jnt_range[calibrated.model.joint(f'{side}_joint{index}').id])


def test_corrections_are_not_applied_to_encoder_wire_values():
    q = [.2,1.,1.3,-.4,.5,-.8]
    measured = {side+'_joints_deg':np.rad2deg(q).tolist() for side in ('left','right')}
    measured.update(left_gripper=.9992793312193716, right_gripper=.0007206687806284)
    state = state_input(measured, 'unchanged task')
    np.testing.assert_allclose(state['state.left_arm'], q, atol=1e-15)
    action = {'q_l_chunk':[state['state.left_arm'] + [.2]]*2,
              'q_r_chunk':[state['state.right_arm'] + [.8]]*2}
    packet = action_waypoints(action, 0)[0]
    np.testing.assert_allclose(packet['left_joints_deg'], measured['left_joints_deg'], atol=1e-13)
    np.testing.assert_allclose(packet['right_joints_deg'], measured['right_joints_deg'], atol=1e-13)


def test_dynamic_selected_profile_changes_binding_and_preserves_both_arms():
    selected = report()
    old = binding_from_report(selected, ROBOHOUSE)
    selected['model_joint_calibration']['calibration_id'] = 'a'*64
    selected['model_joint_calibration']['offsets_rad']['right'][1] += .001
    new = binding_from_report(selected, ROBOHOUSE)
    assert new['fingerprint'] != old['fingerprint']
    assert new['model_calibration_id'] == 'a'*64
    assert new['offsets_rad']['left'] == old['offsets_rad']['left']
    assert new['offsets_rad']['left'] != [0]*6


def test_operator_zero_reference_may_include_j1_and_j6():
    selected = report()
    selected['model_joint_calibration']['calibration_id'] = 'd'*64
    selected['model_joint_calibration']['offsets_rad']['right'] = [-.4,-1.2,-.7,.2,-.1,.6]
    binding = binding_from_report(selected, ROBOHOUSE)
    description = kinematic_description(binding)
    original = BimanualRelativeIK(base_spacing_m=binding['base_spacing_m'])
    original.data.qpos[:12] = binding['offsets_rad']['left'] + binding['offsets_rad']['right']
    mujoco.mj_kinematics(original.model, original.data)
    body = original.model.body('right_grasp').id
    actual = urdf_fk(description['urdfs']['right'], [0.]*6)
    np.testing.assert_allclose(actual[:3,3], original.data.xpos[body]-[0,-binding['base_spacing_m']/2,0], atol=1e-10)


@pytest.mark.parametrize('change', [
    lambda r:r.update(schema_version=2),
    lambda r:r.update(robot_id='another-station'),
    lambda r:r.update(native_joint_calibration={'coordinate_convention':'native_i2rt_updated'}),
    lambda r:r.pop('calibration_id'),
    lambda r:r['model_joint_calibration'].update(canonical_model_sha256='b'*64),
    lambda r:r['model_joint_calibration'].update(coordinate_convention='native_i2rt_updated'),
    lambda r:r['model_joint_calibration']['offsets_rad']['left'].__setitem__(1, float('nan')),
    lambda r:r['model_joint_calibration']['offsets_rad']['right'].__setitem__(1, True),
])
def test_invalid_or_already_native_binding_is_rejected(change):
    selected = copy.deepcopy(report()); change(selected)
    with pytest.raises(ValueError):
        binding_from_report(selected, ROBOHOUSE)


@pytest.mark.parametrize('confirm', [True, False, 'wrong-envelope'])
def test_worker_must_confirm_actual_selected_profile_before_ready(tmp_path, confirm):
    calls = []
    class Worker:
        def __init__(self, *args): pass
        def call(self, command, **payload):
            calls.append((command, payload))
            binding = payload['kinematics']['binding']
            if confirm == 'wrong-envelope':
                return dict(ok=True, result={}, kinematic_calibration=binding)
            return dict(ok=True, result={'kinematic_calibration':binding if confirm else None})
        def close(self): pass
    selected = report()
    provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
        credentials='not-read', python='not-launched', directory=tmp_path,
        camera_source=None, observation_source=lambda:None, robot_id=ROBOHOUSE,
        worker_factory=Worker, calibration_source=lambda:copy.deepcopy(selected))
    provider.configure_robot_workspace(ROBOHOUSE)
    from remote_yam.run_changes import snapshot
    recorded = snapshot(provider, 'same task', 120)
    assert recorded['kinematic_calibration']['model_calibration_id'] == selected['model_joint_calibration']['calibration_id']
    assert recorded['model_calibration_id'] == selected['model_joint_calibration']['calibration_id']
    assert recorded['calibration_id'] == selected['calibration_id']
    provider.start_preparation(lambda:False)
    provider._preparation.join(3)
    assert provider._ready.is_set() is (confirm is True)
    assert [command for command, _ in calls] == ['configure']
    assert calls[0][1]['checkpoint'] == 'dreamlabs/dream-1-beta'
    if confirm is not True:
        assert 'did not confirm' in provider._failure
    selected['model_joint_calibration']['calibration_id'] = 'c'*64
    with pytest.raises(ValueError, match='changed'):
        provider.prepare_after_lease(lambda:False)
    with pytest.raises(ValueError, match='changed'):
        provider.build_trajectory('same task', {}, 0)
    assert [command for command, _ in calls] == ['configure']
    provider.close_transport()


def test_native_other_station_keeps_original_behavior(tmp_path):
    provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
        credentials='not-read', python='not-launched', directory=tmp_path,
        camera_source=None, observation_source=lambda:None, robot_id='yam-1')
    provider.configure_robot_workspace('yam-1')
    assert provider._kinematics is None
    assert 'kinematic_calibration' not in provider.public_config()


@pytest.mark.parametrize('origin', ['https://example.test:9443', 'http://127.0.0.1:8089', 'http://[::1]:8089'])
def test_live_binding_uses_real_camera_source_origin(tmp_path, monkeypatch, origin):
    from remote_yam.cameras import CameraFrameSource, trusted_origin
    from remote_yam import api_depth
    calls = []
    class CalibrationAPI:
        def __init__(self, api_origin, robot_id):
            assert trusted_origin(api_origin) == trusted_origin(origin)
            assert robot_id == ROBOHOUSE
            self.connection = self
        def read(self, suffix, maximum):
            calls.append(suffix)
            return json.dumps(report()).encode()
        def close(self): calls.append('close')
    monkeypatch.setattr(api_depth, 'ApiDepth', CalibrationAPI)
    provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
        credentials='not-read', python='not-launched', directory=tmp_path,
        camera_source=CameraFrameSource(origin), observation_source=lambda:None, robot_id=ROBOHOUSE)
    provider.configure_robot_workspace(ROBOHOUSE)
    assert calls == ['/calibration', 'close']
    assert provider.public_config()['model_calibration_id'] == report()['model_joint_calibration']['calibration_id']
    assert provider._preparation is None


def test_recovery_cannot_silently_switch_to_a_stock_solver(tmp_path):
    calls = []
    class Worker:
        def __init__(self, *args): pass
        def call(self, command, **payload):
            calls.append(command)
            return dict(ok=True, result={'kinematic_calibration':payload['kinematics']['binding'] if len(calls)==1 else None})
        def recover(self, **kwargs): calls.append('recover')
        def close(self): pass
    provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
        credentials='not-read', python='not-launched', directory=tmp_path,
        camera_source=None, observation_source=lambda:None, robot_id=ROBOHOUSE,
        worker_factory=Worker, calibration_source=report)
    provider.configure_robot_workspace(ROBOHOUSE)
    provider.start_preparation(lambda:False); provider._preparation.join(3)
    from remote_yam.dream_policy import DreamWorkerUnavailable
    with pytest.raises(DreamWorkerUnavailable, match='did not confirm'):
        provider._recover_worker(0, 'process_exit')
    assert calls == ['configure','recover','configure']
    provider.close_transport()
