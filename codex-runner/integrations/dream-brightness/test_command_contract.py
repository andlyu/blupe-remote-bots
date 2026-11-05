"""Dream conversion -> real HTTP serializer -> canonical controller parser.

All transports are intercepted. No socket, robot or model request is made.
"""
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

import pytest

from serve import runner_root

ROOT = runner_root(os.environ.get('YAM_DREAM_RUNNER_ROOT'))
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from remote_yam.dream_policy import action_waypoints, motion_limited_waypoints
from remote_yam.session import HttpSessionAPI

CONTROLLER = Path(os.environ.get('YAM_CONTROLLER_SOURCE',
    '/Users/andrew/Projects/blupe-evals/public-projects/blupe-playground-robot-controller'))
SOURCE = Path(os.environ.get('YAM_CANONICAL_TRAJECTORY',
    CONTROLLER / 'src/blupe_controller/runtime/YAM_control/joint_trajectory.py'))
spec = importlib.util.spec_from_file_location('brightness_canonical_trajectory', SOURCE)
canonical = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = canonical
spec.loader.exec_module(canonical)


def observation():
    return dict(left_joints_deg=[.123456789] * 6, right_joints_deg=[-.987654321] * 6,
                left_gripper=.9992793312193716, right_gripper=.0007206687806284)


def through_real_packet_path(points, measured):
    api = HttpSessionAPI('https://offline.invalid', supports_trajectories=True)
    api._session_capabilities['offline-session'] = 'synthetic-no-authority'
    submissions = []
    def transport(method, path, payload, **kwargs):
        serialized = json.dumps(payload, allow_nan=False)
        wire = json.loads(serialized)
        wire.update(type='joint_trajectory', session_id='offline-session', dispatched_at=time.time())
        parsed = canonical.parse_joint_trajectory(wire, expected_session_id='offline-session',
            expected_episode_id='ep_offline', expected_lease_id='offline-lease', expected_step_id=points[0]['step_id'])
        grips = canonical.resolve_gripper_waypoints(parsed,
            left_start=measured['left_gripper'], right_start=measured['right_gripper'])
        submissions.append((parsed, grips))
        return {'accepted':True}
    api._request = transport
    api.submit_trajectory('offline-session', 'ep_offline', 'offline-lease', 'offline-traj', 10, points)
    return submissions


@pytest.mark.parametrize('left,right', [(0.,0.), (1.,1.), (0.,1.), (1.,0.), (.2,.8)])
def test_fractional_starts_exact_numeric_endpoints_and_unchanged_joints(left, right):
    measured = observation()
    action = {key:[math.radians(value) for value in measured[arm+'_joints_deg']] + [grip] for key, arm, grip in
              [('q_l_chunk','left',left), ('q_r_chunk','right',right)]}
    action = {key:[value[:] for _ in range(48)] for key, value in action.items()}
    points = motion_limited_waypoints(action_waypoints(action, 17), measured, 9.)
    parsed, grips = through_real_packet_path(points, measured)[0]
    assert parsed.last_step_id == 17 + len(points) - 1
    assert grips[-1] == (left, right)
    assert all(0 <= grip <= 1 for pair in grips for grip in pair)
    assert all(point.left_joints_deg == pytest.approx(measured['left_joints_deg']) for point in parsed.waypoints)
    assert all(point.right_joints_deg == pytest.approx(measured['right_joints_deg']) for point in parsed.waypoints)
    previous = (measured['left_gripper'], measured['right_gripper'])
    for pair in grips:
        assert max(abs(a-b) for a,b in zip(pair, previous)) <= .3 + 1e-12
        previous = pair


@pytest.mark.parametrize('bad', [-1e-16, 1 + 1e-12, float('nan'), float('inf'), 'bad'])
@pytest.mark.parametrize('arm', ['left','right'])
def test_invalid_serialized_grippers_have_zero_outbound_requests(bad, arm):
    api = HttpSessionAPI('https://offline.invalid', supports_trajectories=True)
    api._session_capabilities['offline-session'] = 'synthetic-no-authority'
    outgoing = []
    api._request = lambda *args, **kwargs: outgoing.append(args)
    point = dict(step_id=0, left_joints_deg=[0.] * 6, right_joints_deg=[0.] * 6,
                 left_gripper=.5, right_gripper=.5)
    point[arm+'_gripper'] = bad
    with pytest.raises((ValueError, TypeError)):
        api.submit_trajectory('offline-session','ep_offline','offline-lease','offline-traj',10,[point])
    assert outgoing == []


def test_local_motion_cap_and_canonical_freshness_and_lease_checks_remain():
    measured = observation()
    action = {'q_l_chunk':[[.2] * 6 + [.5] for _ in range(48)],
              'q_r_chunk':[[-.2] * 6 + [.5] for _ in range(48)]}
    points = motion_limited_waypoints(action_waypoints(action, 0), measured, 9.)
    previous = measured['left_joints_deg'] + measured['right_joints_deg']
    for point in points:
        target = point['left_joints_deg'] + point['right_joints_deg']
        assert max(abs(a-b) for a,b in zip(target, previous)) <= 9. + 1e-12
        previous = target
    through_real_packet_path(points, measured)
    wire = dict(schema_version=1,type='joint_trajectory', session_id='offline-session',episode_id='ep_offline',
                lease_id='wrong-lease',trajectory_id='offline-traj',dispatched_at=time.time(),cadence_hz=10.,waypoints=points)
    kwargs = dict(expected_session_id='offline-session',expected_episode_id='ep_offline',expected_lease_id='offline-lease',expected_step_id=0)
    with pytest.raises(canonical.TrajectorySchemaError, match='lease_mismatch'):
        canonical.parse_joint_trajectory(wire, **kwargs)
    wire.update(lease_id='offline-lease', dispatched_at=time.time()-11)
    with pytest.raises(canonical.TrajectorySchemaError, match='stale_trajectory'):
        canonical.parse_joint_trajectory(wire, **kwargs)
