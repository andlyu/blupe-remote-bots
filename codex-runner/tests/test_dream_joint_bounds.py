"""Calibrated trajectory bounds without changing geometry or collision fences."""
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from remote_yam.dream_joint_bounds import joint_bounds, bind_solver_bounds


def profile():
    # Native order is left, right; SDK order is right, left.
    return joint_bounds([-2.] * 12, [1.5] * 6 + [1.6] * 6)


@dataclass(frozen=True)
class Arm:
    lo: object
    hi: object
    to_pyroki: tuple = (2, 0, 1, 3, 4, 5)
    to_spec: tuple = (1, 2, 0, 3, 4, 5)
    robot: object = None


def test_trajectory_uses_each_native_arm_limit_and_keeps_shared_collision_geometry():
    arm = Arm(np.full(6, -1.9), np.full(6, 1.55), robot=object())
    group = SimpleNamespace(arm=arm, arms=slice(0, 2), obstacles=object())
    solver = SimpleNamespace(sides=('right', 'left'), _groups=[group],
        _side_groups=[group, group], side_lo=np.full((2, 6), -1.9),
        side_hi=np.full((2, 6), 1.55))
    bounds = profile()
    bounds['upper_rad'][0] = 1.3
    bounds['upper_rad'][3] = 1.4
    bind_solver_bounds(solver, bounds, margin=.035)
    # The SDK's tick warm start, FK and inter-arm hard fence retain one group.
    assert solver._groups == [group] and solver._groups[0].arm is arm
    assert solver._side_groups[0] is not solver._side_groups[1]
    assert solver._side_groups[0].arm.robot is arm.robot
    assert solver._side_groups[1].obstacles is group.obstacles
    assert solver.side_hi[0, 3] == 1.55  # Keep a tighter built-in SDK bound.
    assert solver.side_hi[1, 3] == pytest.approx(1.365)
    assert solver._side_groups[1].arm.hi[3] == pytest.approx(1.365)
    assert solver._side_groups[1].arm.hi[1] == pytest.approx(1.265)  # PyRoKi permutation.
    assert np.all(solver.side_lo == -1.9)
    # No mutation of the source arrays or station bounds.
    assert bounds['upper_rad'][3] == 1.4 and np.all(arm.hi == 1.55)


@pytest.mark.parametrize('lo,hi', [([0.]*11,[1.]*12), ([0.]*12,[float('nan')]*12),
    ([False]*12,[1.]*12), ([2.]*12,[1.]*12)])
def test_invalid_native_bounds_fail_before_sdk_preparation(lo, hi):
    with pytest.raises(ValueError):
        joint_bounds(lo, hi)
