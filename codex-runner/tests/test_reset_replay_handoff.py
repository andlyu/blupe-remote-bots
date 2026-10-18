"""Current replay identity wins over stale pose flags; no hardware I/O."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from remote_yam.resets import run_reset
from remote_yam.resets.yam_cube_program import CubeProgram
from remote_yam.resets.yam_cube_reset import ResetBlocked
from remote_yam.resets.yam_tabletop_reset import require_replay_handoff


def completed():
    return dict(request_id='current',phase='complete',running=False,error=None,
                controller_fault=None,completed=2,total=2,finish_action='held',motor_owner='primary_controller')


def controller():
    return dict(mode='STOPPED',launched=True,feedback_available=True,adapter_fault=None,replay=completed(),
        command_source='operator/replay',policy_phase='replay_held',event='Replay complete; arms holding',
        joints=[.2]*12,safety=dict(controller_ok=True,drives_enabled=True),
        auto_queue=dict(enabled=False,running=False),api=dict(authorized=False,session_id=None))


def old_pose():
    return dict(plan_id='old-pose',active=False,sequence_reserved=False,cancelled=True,
                supported_execution_policies=['controller-faults'])


def test_same_preexisting_cancelled_pose_can_follow_its_newly_completed_replay():
    pose=old_pose();prior=copy.deepcopy(pose);s=controller();original=copy.deepcopy((s,pose,prior))
    require_replay_handoff(s,pose,'current',previous_pose=prior)
    assert (s,pose,prior)==original # Never clear the native Stop Event.


@pytest.mark.parametrize('fault',['missing_baseline','new_plan','new_cancel','active','owner',
    'current_stop','current_hold','changed_phase','changed_event','wrong_request','replay_cancelled',
    'disabled','fault','drives_off'])
def test_current_stop_or_unknown_identity_still_prevents_admission(fault):
    s=controller();pose=old_pose();prior=copy.deepcopy(pose)
    if fault=='missing_baseline':prior=None
    elif fault=='new_plan':pose['plan_id']='new-pose'
    elif fault=='new_cancel':prior['cancelled']=False
    elif fault=='active':pose['active']=True
    elif fault=='owner':pose['sequence_reserved']=True
    elif fault=='current_stop':s.update(command_source='operator/stop',event='Stopped by operator')
    elif fault=='current_hold':s.update(command_source='local_pose_operator_hold',event='Trajectory stopped; both arms holding last target: local_pose_operator_hold')
    elif fault=='changed_phase':s['policy_phase']='holding_pose'
    elif fault=='changed_event':s['event']='Replay interrupted; arms holding'
    elif fault=='wrong_request':s['replay']['request_id']='another'
    elif fault=='replay_cancelled':s['replay']['phase']='cancelled'
    elif fault=='disabled':s['mode']='DISABLED'
    elif fault=='fault':s['adapter_fault']='motor fault'
    elif fault=='drives_off':s['safety']['drives_enabled']=False
    with pytest.raises(ResetBlocked):require_replay_handoff(s,pose,'current',previous_pose=prior)


def program(tmp_path,states,*,context=True):
    p=CubeProgram.__new__(CubeProgram);p.out=tmp_path
    p.args=SimpleNamespace(after_replay='current',execution_policy='controller-faults',resume_plan=None,timing_profile='native')
    p.planner=SimpleNamespace(ik=SimpleNamespace(low=np.zeros(12),high=np.ones(12)))
    p.event=Mock();p.io=SimpleNamespace(read=Mock(side_effect=states),call=Mock())
    if context:p.io.reset_replay_handoff=dict(request_id='current',previous_pose=old_pose())
    return p


def test_cube_initializer_uses_only_this_runs_handoff_baseline(tmp_path):
    p=program(tmp_path,[controller(),old_pose(),controller()]);p.initialize()
    assert p.io.read.call_count==3
    p.io.call.assert_not_called() # initialize itself dispatches no motion.


@pytest.mark.parametrize('context',['absent','wrong_request','stop_between_reads'])
def test_cube_initializer_blocks_missing_context_and_stop_during_split_read(tmp_path,context):
    stopped=controller();stopped.update(command_source='local_pose_operator_hold',event='Held by operator')
    p=program(tmp_path,[controller(),old_pose(),stopped if context=='stop_between_reads' else controller()],context=context!='absent')
    if context=='wrong_request':p.io.reset_replay_handoff['request_id']='other'
    with pytest.raises(ResetBlocked):p.initialize()
    p.io.call.assert_not_called()


@pytest.mark.parametrize('stop_during_handoff',[False,True])
def test_combined_sequence_transfers_baseline_and_rechecks_current_stop(tmp_path,stop_during_handoff):
    calls=[]
    class IO:
        last_robot_wall=100.;motion_completed_robot_wall=None
        def __init__(self,*a,**k):self.states=0
        def call(self,op,payload=None):
            calls.append(op)
            if op=='state':
                self.states+=1;s=controller()
                if stop_during_handoff and self.states>=3:s.update(command_source='local_pose_operator_hold',event='Held by operator')
                return s
            if op=='pose_status':return old_pose()
            return completed()
        def close(self):pass
    cube=Mock()
    def run_cube(argv,*,shared_io):
        assert shared_io.reset_replay_handoff==dict(request_id='current',previous_pose=old_pose())
        folder=Path(argv[argv.index('--output')+1]);folder.mkdir()
        (folder/'result.json').write_text(json.dumps(dict(state='complete',goals_reached=True)))
        return 0
    cube.side_effect=run_cube
    cfg=dict(transport=dict(ssh='inert'),io_routes={},replay={},resources={},cube_args=[],
        recipe=dict(schema='abc-replay-edit-v1',episode='physical-1',source_sha256='synthetic',return_home=False,calibration_id='test'))
    result=run_reset(cfg,tmp_path/'run',request_id='current',io_factory=IO,cube_program=cube)
    assert calls.count('replay_start')==1
    assert not any(op in calls for op in ('home','launch','reserve','execute','zero'))
    if stop_during_handoff:
        assert result['state']=='failed';cube.assert_not_called()
    else:
        assert result['goals_reached'];cube.assert_called_once()


@pytest.mark.parametrize('fault',[None,'saved_request','saved_recipe','saved_incomplete','current_hold','current_request'])
def test_confirmed_replay_continuation_never_replays_or_crosses_stop(tmp_path,fault):
    calls=[]
    cfg=dict(transport=dict(ssh='inert-continuation'),io_routes={},replay={},resources={},cube_args=[],
        recipe=dict(schema='abc-replay-edit-v1',episode='physical-1',source_sha256='synthetic',return_home=False,calibration_id='test'))
    prior=tmp_path/'prior';prior.mkdir();saved=completed();recipe=copy.deepcopy(cfg['recipe'])
    if fault=='saved_request':saved['request_id']='wrong'
    if fault=='saved_incomplete':saved['completed']=1
    if fault=='saved_recipe':recipe['source_sha256']='changed'
    for name,record in [('before.json',dict(local_pose=old_pose())),('replay-result.json',saved),('selected-replay.json',recipe)]:
        (prior/name).write_text(json.dumps(record))
    class IO:
        last_robot_wall=100.;motion_completed_robot_wall=None
        def __init__(self,*a,**k):pass
        def call(self,op,payload=None):
            calls.append(op)
            if op=='state':
                result=controller()
                if fault=='current_hold':result.update(command_source='local_pose_operator_hold',event='Held by operator')
                if fault=='current_request':result['replay']['request_id']='different'
                return result
            if op=='pose_status':return old_pose()
            if op=='replay_start':raise AssertionError('Continuation must not dump the box again')
            return completed()
        def close(self):pass
    cube=Mock()
    def run_cube(argv,*,shared_io):
        assert shared_io.reset_replay_handoff['previous_pose']==old_pose()
        folder=Path(argv[argv.index('--output')+1]);folder.mkdir()
        (folder/'result.json').write_text(json.dumps(dict(state='complete',goals_reached=True)));return 0
    cube.side_effect=run_cube
    result=run_reset(cfg,tmp_path/'new',request_id='current',continue_after_replay=prior,io_factory=IO,cube_program=cube)
    assert 'replay_start' not in calls
    if fault is None:
        assert result['goals_reached'] and result['timings']['replay_command_wall_s']==0.
        cube.assert_called_once()
        receipt=json.loads((tmp_path/'new/continued-replay.json').read_text())
        assert receipt['replay_dispatched'] is False and len(receipt['input_sha256'])==3
    else:
        assert result['state']=='failed';cube.assert_not_called()
