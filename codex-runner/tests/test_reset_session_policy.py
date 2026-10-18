"""Reset joins the normal queue and never takes the manual pose owner."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import numpy as np

from remote_yam.controller import RunnerController
from remote_yam.resets.session_policy import CubeSessionPolicy, SessionResetIO
from remote_yam.resets.yam_cube_program import CubeProgram
from remote_yam.session import MockSessionAPI

CONTEXT=dict(session_id='session',episode_id='episode',lease_id='lease',robot_id='yam-1')


def state():
    return dict(mode='API_ACTIVE',homed=True,settled=True,joints=[0.]*12,
        safety=dict(controller_ok=True,drives_enabled=True),adapter_fault=None,
        auto_queue=dict(enabled=True,running=False),
        api=dict(authorized=True,session_id='session',episode_id='episode'),
        cube_reset_session=dict(enabled=True,protocol='cube-session-pose-v1',
            execution_policy='controller-faults',lease_id='lease'))


class Camera:
    last_robot_wall=1.;needs_reconnect=False;before_request=None
    def __init__(self,*args,**kwargs):self.calls=[];self.current=state()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,op):
        if self.before_request:self.before_request()
        self.calls.append(op)
        assert op=='state'
        return deepcopy(self.current)
    call=read
    def reconnect(self):pass


class API:
    def __init__(self):self.calls=[];self.result={};self.plans=0
    def _capability(self,sid):assert sid=='session';return 'private-capability'
    def _request(self,method,path,body=None,**kwargs):
        assert kwargs['bearer']=='private-capability'
        self.calls.append((method,path,body))
        if method=='POST':
            assert body['lease_id']=='lease' and body['executor']=='yam_cube_reset'
            assert 'owner_token' not in body['payload']
            op=body['operation'];self.plans+=op=='execute'
            value=dict(state='previewed' if op=='preview' else 'holding',plan_id='plan',
                execution_policy='controller-faults',completion_wait_supported=True)
            self.result[body['request_id']]=dict(status='completed',result=value)
            return dict(status='pending')
        return self.result[path.rsplit('/',1)[-1]]
    def stop_session(self,sid,**kwargs):self.calls.append(('STOP',sid,kwargs))


def bridge():
    return SessionResetIO(Camera(),API(),CONTEXT,cancelled=lambda:False,
                          execution_policy='controller-faults')


def test_enabled_auto_queue_initialization_uses_existing_home_and_no_manual_start(tmp_path):
    io=bridge();program=CubeProgram.__new__(CubeProgram)
    program.io=io;program.args=SimpleNamespace(execution_policy='controller-faults')
    program.out=tmp_path;program.event=Mock()
    program.initialize()
    assert program.startup_needs_planning_home is False
    assert io.camera.calls==['state']
    assert [c[2]['operation'] for c in io.api.calls if c[0]=='POST']==['status']
    assert io.camera.current['auto_queue']['enabled']


def test_motion_only_uses_matching_session_executions():
    io=bridge();reserved=io.call('reserve',{'execution_policy':'controller-faults'})
    token=reserved['owner_token']
    p=io.call('preview',dict(owner_token=token,joints_rad=[.1]*12,grippers=[.5,.5]))
    io.call('execute',dict(owner_token=token,plan_id=p['plan_id']))
    io.call('wait',dict(owner_token=token,plan_id=p['plan_id'],timeout_s=2))
    io.call('release',dict(owner_token=token))
    assert io.api.plans==1
    assert all(c=='state' for c in io.camera.calls)
    assert io.camera.current['auto_queue']['enabled']
    assert io.camera.current['api']['authorized']


@pytest.mark.parametrize('change',[{'mode':'DISABLED'},
    {'api':dict(authorized=True,session_id='other',episode_id='episode')},
    {'cube_reset_session':dict(enabled=True,protocol='cube-session-pose-v1',execution_policy='controller-faults',lease_id='old')}])
def test_stopped_or_replaced_session_never_reserves_or_initializes(change):
    io=bridge();io.camera.current.update(change)
    with pytest.raises(KeyboardInterrupt):io.call('reserve',{'execution_policy':'controller-faults'})
    assert io.api.calls==[]


def test_stop_latch_prevents_later_execution():
    io=bridge();io.cancelled=lambda:True
    with pytest.raises(KeyboardInterrupt):io.call('preview',{})
    assert io.api.calls==[]


def test_lost_execute_ack_is_not_reposted():
    io=bridge();token=io.call('reserve',{'execution_policy':'controller-faults'})['owner_token']
    p=io.call('preview',dict(owner_token=token,joints_rad=[.1]*12,grippers=[.5,.5]))
    original=io.api._request
    def lost(method,path,body=None,**kwargs):
        result=original(method,path,body,**kwargs)
        if method=='POST' and body['operation']=='execute':raise TimeoutError('ack lost')
        return result
    io.api._request=lost
    with pytest.raises(TimeoutError):io.call('execute',dict(owner_token=token,plan_id=p['plan_id']))
    io.call('wait',dict(owner_token=token,plan_id=p['plan_id'],timeout_s=2))
    assert io.api.plans==1


def test_camera_clock_receipts_follow_queue_home_and_completed_motion():
    io=bridge();io.camera.last_robot_wall=10.
    token=io.call('reserve',{'execution_policy':'controller-faults'})['owner_token']
    assert io.motion_completed_robot_wall==10.
    p=io.call('preview',dict(owner_token=token,joints_rad=[.1]*12,grippers=[.5,.5]))
    io.call('execute',dict(owner_token=token,plan_id=p['plan_id']))
    io.camera.last_robot_wall=20.
    io.call('wait',dict(owner_token=token,plan_id=p['plan_id'],timeout_s=2))
    assert io.motion_completed_robot_wall==20.
    assert io.api.plans==1


def test_stop_after_motion_ack_blocks_the_camera_continuation():
    io=bridge();token=io.call('reserve',{'execution_policy':'controller-faults'})['owner_token']
    p=io.call('preview',dict(owner_token=token,joints_rad=[.1]*12,grippers=[.5,.5]))
    io.call('execute',dict(owner_token=token,plan_id=p['plan_id']))
    io.camera.current['mode']='DISABLED'
    with pytest.raises(KeyboardInterrupt):
        io.call('wait',dict(owner_token=token,plan_id=p['plan_id'],timeout_s=2))
    assert io.api.plans==1


@pytest.mark.parametrize('outcome,goals,reason',[('complete',True,'policy_complete'),
                                              ('cancelled',False,'user_requested')])
def test_provider_joins_normal_queue_and_session_completion_uses_normal_stop(tmp_path,outcome,goals,reason):
    config=tmp_path/'station.json'
    config.write_text(json.dumps(dict(resources={},io_routes={},transport=dict(ssh='inert'))))
    calls=[]
    def run(config,output,**kwargs):
        calls.append(kwargs['shared_io'].context)
        return dict(state=outcome,goals_reached=goals,request_id=kwargs['request_id'])
    policy=CubeSessionPolicy('reset_bin',dict(model='cube-reset-session-v1',label='Reset bin',
        task='Reset bin',session_config=str(config)),tmp_path,io_factory=Camera,cube_runner=run)
    api=MockSessionAPI();api.stop_session=Mock(wraps=api.stop_session);controller=RunnerController(api)
    controller.join_and_run(policy,'Reset bin')
    deadline=time.monotonic()+3
    while controller._worker.is_alive() and time.monotonic()<deadline:time.sleep(.01)
    assert not controller._worker.is_alive()
    assert len(api.create_requests)==1
    assert len(calls)==1, controller.status()['error']
    assert calls[0]['session_id']==controller.status()['session_id']
    assert policy.public_config()['managed_execution']['phase']==outcome
    assert controller.status()['error'] is None
    assert api.stop_session.call_args.kwargs['reason']==reason


def test_cube_runner_accepts_injected_session_io_in_worker_thread(tmp_path):
    from remote_yam.resets.cube_runner import run_cube_reset
    config=dict(resources={},io_routes={},replay={},recipe={},transport=dict(ssh='inert'),cube_args=[])
    io=object();results=[]
    def cube(argv,*,shared_io):
        assert shared_io is io
        output=Path(argv[argv.index('--output')+1]);output.mkdir()
        (output/'result.json').write_text(json.dumps(dict(state='complete',goals_reached=True)))
        return 0
    thread=threading.Thread(target=lambda:results.append(run_cube_reset(config,tmp_path/'run',cube_main=cube,shared_io=io)))
    thread.start();thread.join(3)
    assert not thread.is_alive() and results[0]['goals_reached']


@pytest.mark.parametrize('outcome', ['complete','failed','cancelled','uncertain','stop_at_handoff','home_failed'])
def test_recorded_sequence_orders_replay_home_cube_and_stop_wins(tmp_path,outcome):
    from remote_yam.resets.session_policy import RESET_SEQUENCE
    config=tmp_path/'station.json'
    recipe=dict(schema='abc-replay-edit-v1',episode='physical-123',return_home=False,
                source_sha256='source',calibration_id='native',start_s=20,end_s=90,speed=2)
    config.write_text(json.dumps(dict(resources={},io_routes={},transport=dict(ssh='inert'),recipe=recipe)))
    calls=[]; stopped=threading.Event()
    class SequenceIO(SessionResetIO):
        def sequence_motion(self,kind,**kwargs):
            self.check_cancelled(); calls.append(kind)
            if kind=='recorded_replay':
                if outcome=='uncertain':raise TimeoutError('uncertain, never retry')
                if outcome=='cancelled':raise KeyboardInterrupt('Stop')
                if outcome=='stop_at_handoff':stopped.set()
                replay=dict(request_id=kwargs['request_id'],phase='failed' if outcome=='failed' else 'complete',
                    running=False,total=10,completed=10,finish_action='held',motor_owner='primary_controller')
                return dict(state='holding',replay_result=replay)
            return dict(state='holding',reached_target=outcome!='home_failed')
    class C(Camera):
        def __init__(self,*args,**kwargs):
            super().__init__();self.current['cube_reset_session']['recorded_replay_supported']=True
    def cube(config,output,**kwargs):
        kwargs['shared_io'].check_cancelled();calls.append('cube_reset');output.mkdir()
        return dict(state='complete',goals_reached=True)
    policy=CubeSessionPolicy('reset_bin',dict(model='sequence',label='Reset bin',task='Reset bin',
        session_config=str(config),sequence=RESET_SEQUENCE,execution_policy='controller-faults'),
        tmp_path,io_factory=C,cube_runner=cube)
    api=API()
    from unittest.mock import patch
    with patch('remote_yam.resets.session_policy.SessionResetIO',SequenceIO):
        if outcome in ('failed','uncertain','home_failed'):
            with pytest.raises(Exception):policy.run_session('Reset bin',{},api,CONTEXT,stopped.is_set)
        else:
            policy.run_session('Reset bin',{},api,CONTEXT,stopped.is_set)
    assert calls==(['recorded_replay','camera_clear_home','cube_reset'] if outcome=='complete' else
                   ['recorded_replay','camera_clear_home'] if outcome=='home_failed' else ['recorded_replay'])
    if outcome!='complete': assert any(c[0]=='STOP' for c in api.calls)
    if outcome in ('cancelled','stop_at_handoff'):assert policy._phase=='cancelled'
    if outcome=='complete':assert policy._result['replay_requested'] and policy._result['sequence']==RESET_SEQUENCE


def test_sequence_execute_ack_loss_is_never_reposted():
    io=bridge();original=io.api._request
    def lost(method,path,body=None,**kwargs):
        value=original(method,path,body,**kwargs)
        if method=='POST' and body['operation']=='execute':raise TimeoutError('ack lost')
        return value
    io.api._request=lost
    with pytest.raises(TimeoutError):io.sequence_motion('recorded_replay',recipe={},request_id='a'*32)
    assert io.api.plans==1


def test_real_wrist_consumer_collects_distinct_frames_through_session_checks(tmp_path,monkeypatch):
    from remote_yam.resets.yam_cube_program import wrist_rows
    import remote_yam.api_depth as depth
    import remote_yam.resets.kinematics as kinematics
    io=bridge();io.motion_completed_robot_wall=100.
    rgb=np.zeros((32,32,3),dtype=np.uint8);rgb[:,:,2]=255
    frames=[SimpleNamespace(rgb=rgb,depth=np.full((32,32),.1),
        metadata=dict(sequence=index,captured_at=100.+index),age_upper_s=.1) for index in (1,1,2,3)]
    calls=[]
    def capture(report,**kwargs):
        calls.append(kwargs)
        assert io.camera.motion_completed_robot_wall==100.
        return frames.pop(0)
    io.camera.capture=capture
    monkeypatch.setattr(depth,'factory_ray',lambda profile,u,v:np.array([u*.001,v*.001,1.]))
    monkeypatch.setattr(kinematics,'arm_pose',lambda *args:np.eye(4))
    report=dict(cameras=dict(left=dict(T_grasp_camera=np.eye(4).tolist(),depth_intrinsics={})))
    rows,after=wrist_rows(io,report,'blue','left',tmp_path/'wrist',count=3)
    assert [r['sequence'] for r in rows]==[1,2,3]
    assert len(calls)==4 and all(c['camera']=='left' for c in calls)
    assert io.camera.calls==['state']*6  # Before/after plus each attempted frame.
    assert after['api']['authorized'] and io.api.calls==[]


@pytest.mark.parametrize('stop',['callback','lease'])
def test_multi_frame_wrist_capture_stops_before_the_next_frame(stop):
    io=bridge();calls=[]
    def capture(report,**kwargs):
        calls.append(kwargs)
        if stop=='callback':io.cancelled=lambda:True
        else:io.camera.current['api']['authorized']=False
        return SimpleNamespace(metadata=dict(sequence=1,captured_at=1.))
    io.camera.capture=capture
    with pytest.raises(KeyboardInterrupt):io.captures({},count=3,camera='right',after_robot_wall=.5)
    assert len(calls)==1 and calls[0]==dict(camera='right',after_robot_wall=.5)
    assert io.api.calls==[]
