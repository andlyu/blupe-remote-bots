import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from remote_yam.controller_dream_overlap import run_overlap


def setup(deny=False):
    checks, commands = [], []
    canceled = threading.Event()
    context = ('session', 'episode', 'lease')
    op = SimpleNamespace(lock=threading.RLock(), _hardware_pending=None,
                         api_last_step=-1, api_observation_step=0)
    snap = SimpleNamespace(left=SimpleNamespace(joints_rad=(0.,)*6),
                           right=SimpleNamespace(joints_rad=(0.,)*6))
    def approve(previous, points, **kwargs):
        checks.append((len(points), kwargs))
        if deny: raise ValueError('rejected before motion')
        return SimpleNamespace(waypoints=points)
    physical = SimpleNamespace(last_command=None, snapshot=lambda: snap)
    def execute(points, **kwargs):
        assert kwargs['wait_for_settle'] is False
        assert kwargs['cadence_hz'] == 10
        assert kwargs['cancel_event'] is canceled
        approved = kwargs['validate_waypoint'](0, (0.,)*12, points[0])
        commands.append(approved)
        physical.last_command = dict(joints=approved, grippers=(.3, .7))
        kwargs['on_waypoint'](0)
    physical.execute = execute
    op._physical = physical
    op._safety_guardrails = SimpleNamespace(approve=approve)
    native = SimpleNamespace(cancel=canceled, observation=lambda: {})
    def build(*args):
        assert args[-1] == 0  # Predictions cannot reserve executed step IDs.
        adapter.last_probe = dict(input_monotonic=time.monotonic(), waypoint_count=24)
        return [dict(left_joints_deg=[.01]*6, right_joints_deg=[.02]*6,
                     left_gripper=.3, right_gripper=.7) for _ in range(24)]
    adapter = SimpleNamespace(_max_commands=2, build_trajectory=build,
                              last_probe=None, close_transport=lambda: canceled.set())
    native.adapter = adapter
    executor = SimpleNamespace(operator=op, context=context, lock=threading.RLock(),
        _cancelled=lambda: False, waypoints=0, predictions=0, predicted_waypoints=0)
    return executor, native, op, checks, commands


def test_overlap_reuses_native_checks_and_counts_only_dispatched_steps():
    executor, native, op, checks, commands = setup()
    run_overlap(executor, native, {'task': 'hold'})
    assert len(commands) == executor.waypoints == 2
    assert op.api_last_step == 1 and op.api_observation_step == 2
    assert checks[0][0] == 24 and [c[0] for c in checks[1:]] == [1, 1]
    assert all(c[1]['target_limit_tolerance_rad'] == .001 for c in checks)
    assert executor.overlap_loop.thread.is_alive() is False
    assert native.cancel.is_set()
    assert native.adapter.commanded_source()['q_l_chunk'] == pytest.approx(
        [np.deg2rad(.01)]*6 + [.3])


def test_unsafe_later_point_prevents_any_native_command():
    executor, native, op, checks, commands = setup(deny=True)
    with pytest.raises(ValueError, match='rejected before motion'):
        run_overlap(executor, native, {'task': 'hold'})
    assert not commands and op.api_last_step == -1
    assert native.cancel.is_set()


def test_existing_native_command_prevents_overlap_start():
    executor, native, op, checks, commands = setup()
    op._hardware_pending = {'busy': True}
    with pytest.raises(RuntimeError, match='already|active'):
        run_overlap(executor, native, {'task': 'hold'})
    assert not commands and not checks
