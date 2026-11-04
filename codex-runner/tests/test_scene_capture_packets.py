"""Actual minute generator/serializer, chunk completion and fail-closed starts."""
import io
import json
from pathlib import Path
import time
from unittest.mock import patch

import numpy as np
import pytest
from remote_yam.providers import PolicyComplete
from remote_yam.session import HttpSessionAPI
from remote_yam.scene_capture_policy import MinutePolicy,TASK
from remote_yam.scene_capture_flow import DEFAULTS

ROOT=Path(__file__).parents[1]/'scene-capture-data'

def setup(grip=.9992793312193716):
    report=json.loads((ROOT/'yam1-calibration.json').read_text())
    home=json.loads((ROOT/'simulation-home.json').read_text())['home_pose']
    obs=dict(source='simulation',robot_id='yam-1',homed=True,settled=True,safety=dict(ok=True),
        observed_at=time.time(),episode_id='offline-minute',lease_id='offline-only',step_id=0,
        left_joints_deg=np.rad2deg(home[:6]).tolist(),right_joints_deg=np.rad2deg(home[7:13]).tolist(),
        left_gripper=grip,right_gripper=.9947321472782467 if grip!=0 else 0.)
    return MinutePolicy(report,DEFAULTS,simulation=True),obs

def completed(obs,points):
    return {**obs,**points[-1], 'step_id':points[-1]['step_id']+1,'homed':False,'observed_at':time.time()}

@pytest.mark.parametrize('grip',[0.,1.,.37,.9992793312193716])
def test_two_real_packets_finish_at600_and_preserve_measured_grippers(grip):
    p,obs=setup(grip);api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True,robot_id='yam-1')
    api._session_capabilities['offline']='offline-only';sent=[]
    def wire(req,**kwargs):
        sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
    with patch('remote_yam.session.request.urlopen',side_effect=wire):
        for cursor in [0,300]:
            obs['observed_at']=time.time()
            points=p.build_trajectory(TASK,obs,cursor)
            assert len(points)==300 and points[0]['step_id']==cursor and points[-1]['step_id']==cursor+299
            api.submit_trajectory('offline',obs['episode_id'],obs['lease_id'],str(cursor),10.,points)
            assert all(point['left_gripper']==grip and point['right_gripper']==obs['right_gripper'] for point in points)
            with pytest.raises(RuntimeError):p.build_trajectory(TASK,obs,cursor)
            final=completed(obs,points)
            if cursor==0:
                with pytest.raises(RuntimeError):p.validate_trajectory_final({**final,'lease_id':'wrong'})
                with pytest.raises(RuntimeError):p.validate_trajectory_final({**final,'step_id':299})
            p.validate_trajectory_final(final);obs=final
            assert p.complete==(cursor==300)
    assert len(sent)==2 and sum(len(s['waypoints']) for s in sent)==600
    with pytest.raises(PolicyComplete):p.build_trajectory(TASK,obs,600)

@pytest.mark.parametrize('change',[dict(source='hardware'),dict(homed=False),dict(settled=False),
    dict(safety=dict(ok=False)),dict(observed_at=0),dict(robot_id='other'),dict(left_gripper=-1e-16),
    dict(left_gripper=1+1e-15),dict(left_gripper=float('nan')),dict(right_gripper=float('inf')),
    dict(left_joints_deg=[float('nan')]*6),dict(lease_id=None)])
def test_invalid_start_has_no_plan_or_dispatch(change):
    p,obs=setup();sent=[]
    with patch('remote_yam.session.request.urlopen',side_effect=lambda *a,**k:sent.append(a)):
        with pytest.raises((ValueError,RuntimeError)):p.build_trajectory(TASK,{**obs,**change},0)
    assert sent==[] and p.route is None and p.pending is None

def test_second_packet_rejects_measured_deviation_and_never_replays():
    p,obs=setup();points=p.build_trajectory(TASK,obs,0);final=completed(obs,points)
    p.validate_trajectory_final(final)
    final['left_joints_deg'][0]+=6
    with pytest.raises(ValueError):p.build_trajectory(TASK,final,300)
    assert p.pending is None and not p.complete

def test_stop_before_planning_has_no_route():
    p,obs=setup();p.cancelled=lambda:True
    with pytest.raises(RuntimeError):p.build_trajectory(TASK,obs,0)
    assert p.route is None and p.pending is None
