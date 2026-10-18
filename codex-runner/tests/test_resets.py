"""Public-only reset execution and pick/place/replay regressions; inert hardware."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from remote_yam.resets import run_reset
from remote_yam.resets.yam_cube_reset import ResetBlocked,measured_top_face
from remote_yam.resets.yam_cube_grasps import aperture_for_gap
from remote_yam.resets.yam_cube_program import CubeProgram
from remote_yam.resets.recorded_replay import plan
from remote_yam.resets.replay_edit import preview


def config():
    return dict(transport=dict(ssh='stub-controller'),io_routes={},replay=dict(controller_origin='http://localhost'),
        recipe=dict(schema='abc-replay-edit-v1',episode='physical-1',source_sha256='synthetic-source',
                    start_s=0.,end_s=1.,speed=1.,return_home=False,calibration_id='synthetic-calibration'),
        resources={},cube_args=['--runtime-root','.'])


def replay(request_id='example',**overrides):
    result=dict(phase='complete',running=False,error=None,controller_fault=None,completed=2,total=2,
                request_id=request_id,finish_action='held',motor_owner='primary_controller')
    result.update(overrides);return result


def state(current):
    return dict(mode='STOPPED',launched=True,feedback_available=True,adapter_fault=None,replay=current,
                safety=dict(controller_ok=True,drives_enabled=True),auto_queue=dict(enabled=False,running=False),
                api=dict(authorized=False,session_id=None))


def test_public_combined_entry_point_uses_one_connection_and_no_stage_launchers(tmp_path):
    calls=[];connections=[]
    class IO:
        last_robot_wall=100.;motion_completed_robot_wall=None
        def __init__(self,*args,**kw):
            connections.append(self);compile(kw['worker_source'],'public-reset-worker','exec')
            assert 'blupe_evals' not in kw['worker_source']
        def call(self,op,payload=None):
            if self.before_request:self.before_request()
            calls.append(op)
            if op=='state':return state(replay())
            if op=='pose_status':return dict(active=False,sequence_reserved=False,cancelled=False)
            return replay()
        def close(self):calls.append('close')
    def cube(argv,*,shared_io):
        assert shared_io is connections[0]
        calls.append('cube-in-process')
        output=Path(argv[argv.index('--output')+1]);output.mkdir()
        (output/'result.json').write_text(json.dumps(dict(state='complete',goals_reached=True)))
        return 0
    result=run_reset(config(),tmp_path/'run',request_id='example',io_factory=IO,cube_program=cube)
    assert result['goals_reached']
    assert len(connections)==1 and calls.count('replay_start')==1 and calls.count('cube-in-process')==1
    assert not any(op in calls for op in ('launch','home','zero','park'))
    assert json.loads((tmp_path/'run/status.json').read_text())['phase']=='complete'


@pytest.mark.parametrize('change',[dict(phase='failed'),dict(completed=1),dict(request_id='other')])
def test_uncertain_replay_cannot_launch_cube(tmp_path,change):
    calls=[]
    class IO:
        last_robot_wall=100.
        def __init__(self,*a,**k):pass
        def call(self,op,payload=None):
            if self.before_request:self.before_request()
            calls.append(op)
            if op=='state':return state(replay())
            if op=='pose_status':return dict(active=False,sequence_reserved=False,cancelled=False)
            return replay(**change)
        def close(self):pass
    cube=Mock()
    result=run_reset(config(),tmp_path/'run',request_id='example',io_factory=IO,cube_program=cube)
    assert result['state']=='failed';cube.assert_not_called();assert calls.count('replay_start')==1


def test_cancel_before_start_never_opens_hardware(tmp_path):
    factory=Mock()
    result=run_reset(config(),tmp_path/'run',cancelled=lambda:True,io_factory=factory)
    assert result['state']=='cancelled';factory.assert_not_called()


def test_existing_cube_initialize_cannot_relaunch_after_stop(tmp_path):
    program=CubeProgram.__new__(CubeProgram)
    program.args=SimpleNamespace(after_replay='example',execution_policy='controller-faults');program.out=tmp_path
    stopped=state(replay());stopped['mode']='DISABLED'
    program.io=SimpleNamespace(read=Mock(side_effect=[stopped,dict(active=False,sequence_reserved=False,cancelled=False)]))
    with pytest.raises(ResetBlocked,match='will not initialize'):program.initialize()


def test_actual_grasp_gap_and_recorded_crop_implementations():
    reference=dict(closed_gap_m=-.001,opening_travel_m=.095)
    assert aperture_for_gap(.04,reference)*.095-.001==pytest.approx(.04)
    with pytest.raises(ResetBlocked):aperture_for_gap(.2,reference)
    actions=np.zeros((3,14));actions[:,6]=actions[:,13]=.5;actions[1,0]=.1
    source=dict(episode='physical-1',actions=actions.tolist(),times=[0.,.5,1.],source_sha256='synthetic')
    recipe=dict(start_s=0.,end_s=1.,speed=1.,return_home=False)
    no_home=preview(source,recipe,[0.]*12);with_home=preview(source,dict(recipe,return_home=True),[0.]*12)
    np.testing.assert_array_equal(np.array(with_home['actions'])[:len(no_home['actions'])],no_home['actions'])
    assert no_home['generated_home_seconds']==0
    assert plan(source).shape[1]==14


def test_actual_rgbd_top_fit_uses_measured_surface():
    x,y=np.meshgrid(np.linspace(-.015,.015,21),np.linspace(-.015,.015,21))
    surface=SimpleNamespace(cloud=np.dstack([x+.28,y-.19,.03+.02*x]),valid=np.ones(x.shape,bool))
    fit=measured_top_face(surface,surface.valid,.03)
    np.testing.assert_allclose(fit['center'],[.28,-.19,.03],atol=1e-7)


def test_failed_pickup_planning_still_records_planning_time(tmp_path,monkeypatch):
    from remote_yam.resets.yam_cube_size_profile import SizeAwarePlanning
    import remote_yam.resets.yam_cube_size_profile as profile
    program=SizeAwarePlanning();program.out=tmp_path;program.report={};program.planner=object();program.targets={}
    scene={color:dict(color=color) for color in ('blue','orange','yellow')}
    program.scene=lambda name:copy.deepcopy(scene);program.state=lambda:{}
    events=[];program.event=lambda event,**values:events.append(dict(event=event,**values))
    monkeypatch.setattr(profile,'fit_scene_nonpenetration',lambda scene,report:scene)
    monkeypatch.setattr(profile,'retarget_source',Mock(side_effect=ResetBlocked('reference failed')))
    program.make_plan=Mock(side_effect=ResetBlocked('fresh plan failed'))
    with pytest.raises(ResetBlocked):program.run_pickup_feedback(scene,[dict(color='blue')])
    timing=[event for event in events if event['event']=='planning_timing']
    assert len(timing)==1 and timing[0]['wall_s']>=0
