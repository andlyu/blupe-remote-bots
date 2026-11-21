"""Regression for post-sweep Home state and next-command completion cursor."""
import json
from pathlib import Path
import time
import numpy as np
import pytest
from scene_video import SweepPolicy, TASK

ROOT=Path(__file__).resolve().parent

def pending():
    report=json.loads((ROOT/'data/yam1-calibration.json').read_text())
    home=[-.024,.794,.645,-.375,-.021,-.012]
    obs=dict(source='simulation',robot_id='yam-1',homed=True,settled=True,safety=dict(ok=True),
        observed_at=time.time(),episode_id='regression',lease_id='offline-only',step_id=0,
        left_joints_deg=np.rad2deg(home).tolist(),right_joints_deg=np.rad2deg(home).tolist(),
        left_gripper=.9992793312193716,right_gripper=.9947321472782467)
    policy=SweepPolicy(report,simulation=True)
    points=policy.build_trajectory(TASK,obs,0)
    final={**obs,**points[-1],'homed':False,'step_id':points[-1]['step_id']+1,'observed_at':time.time()}
    return policy,final

def test_completed_sweep_is_away_from_home_and_reports_next_cursor():
    policy,final=pending()
    policy.validate_trajectory_final(final)
    assert policy.complete

@pytest.mark.parametrize('change',[dict(step_id=119),dict(lease_id='wrong'),dict(safety=dict(ok=False)),
    dict(settled=False),dict(observed_at=0),dict(left_joints_deg=[0]*6)])
def test_invalid_completion_remains_rejected(change):
    policy,final=pending()
    with pytest.raises((ValueError,RuntimeError)):
        policy.validate_trajectory_final({**final,**change})
    assert not policy.complete
