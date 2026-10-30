import threading
import time
import sys
from types import ModuleType
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
        assert kwargs['cadence_hz'] == 10
        assert kwargs['cancel_event'] is canceled
        approved = kwargs['validate_waypoint'](0, (0.,)*12, points[0])
        commands.append(approved)
        physical.last_command = dict(joints=approved, grippers=(.3, .7))
        if kwargs.get('on_waypoint'):
            kwargs['on_waypoint'](0)
            assert kwargs['wait_for_settle'] is False
        else:
            assert kwargs['wait_for_settle'] is True
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
    assert len(commands) == 3 and executor.waypoints == 2  # final measured settle retains last target
    assert op.api_last_step == 1 and op.api_observation_step == 2
    assert checks[0][0] == 24 and [c[0] for c in checks[1:]] == [1, 1, 1]
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


@pytest.mark.parametrize('code', ['adjacent_delta_limit', 'joint_velocity_limit',
                                  'right_tip_outside_workspace'])
def test_handoff_rejected_after_plan_validation_retains_native_hold(monkeypatch, code):
    """Feedback can move between plan approval and the native callback."""
    import remote_yam.controller_dream_overlap as module
    from remote_yam.dream_overlap import PlanRejected
    executor, native, op, checks, commands = setup()
    native.adapter._changed = threading.RLock()
    feedback = []
    native.adapter.trajectory_failed = lambda *args: feedback.append(args)
    dispatching = False
    held = []

    class Boundary(ValueError):
        def __init__(self):
            self.code = code
            super().__init__(code)

    class WaypointSafetyRejected(RuntimeError):
        def __init__(self, waypoint, code):
            self.waypoint, self.code = waypoint, code
            super().__init__(code)

    fake_driver = ModuleType('YAM_control.i2rt_bimanual_adapter')
    fake_driver.WaypointSafetyRejected = WaypointSafetyRejected
    monkeypatch.setitem(sys.modules, 'YAM_control.i2rt_bimanual_adapter', fake_driver)

    def approve(previous, points, **kwargs):
        if dispatching:
            raise Boundary()
        return SimpleNamespace(waypoints=points)

    op._safety_guardrails.approve = approve

    def execute(points, **kwargs):
        # Mirrors the native driver's typed hold path; any other exception
        # escapes as a failure rather than being mistaken for a safe dispatch.
        try:
            kwargs['validate_waypoint'](0, (.2,)*12, points[0])
        except WaypointSafetyRejected as error:
            held.append(error.code)
            raise
        pytest.fail('Rejected target must never reach the motors')

    op._physical.execute = execute

    class ForcedHandoff:
        def __init__(self, *, predict, play, **kwargs):
            self.predict, self.play = predict, play
            self.waypoints, self.thread = 0, None

        def run(self):
            nonlocal dispatching
            points, _ = self.predict()  # Whole plan initially passes.
            dispatching = True          # Force changed feedback at dispatch.
            with pytest.raises(PlanRejected):
                self.play(points[0])

    monkeypatch.setattr(module, 'OverlapLoop', ForcedHandoff)
    run_overlap(executor, native, {'task': 'hold'})
    assert held == [code]
    assert feedback[0][0] == code
    assert op.api_last_step == -1 and not commands
    assert native.cancel.is_set()
