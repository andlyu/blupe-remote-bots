import base64
from copy import deepcopy
import hashlib
import threading
import time
from unittest.mock import patch

import pytest
import numpy as np

from remote_yam.cameras import CameraFrame
from remote_yam.controller import RunnerController
from remote_yam.home_scene import HomePlan, decode_scene, profile_key
from remote_yam.robocurve_policy import OpenAIAdapter
from remote_yam.session import MockSessionAPI
from test_robocurve_policy import observation, response

JPEG = b'\xff\xd8unchanged\xff\xd9'


def scene():
    now = time.time()
    obs = {**observation(), 'source':'hardware','jetson_id':'yam-1','homed':True,
           'observed_at':now, 'left_gripper':1.,'right_gripper':1.}
    return dict(version=1, robot_id='yam-1', scene_id='scene-1', boot_id='boot-1',
        config_sha256='a'*64,captured_at=now,observation=obs,
        frames={name:dict(jpeg_base64=base64.b64encode(JPEG).decode(),
            sha256=hashlib.sha256(JPEG).hexdigest(), captured_at=now)
            for name in ('left','top','right')})


class Cameras:
    jpeg = JPEG
    timestamp = True
    def capture(self,obs):
        return [CameraFrame(name,self.jpeg,time.time(),source_captured_at=time.time() if self.timestamp else None)
                for name in ('left','top','right')]


def setup():
    api = MockSessionAPI(auto_activate=False)
    api.scene = scene()
    api.ready = False
    api.reports = []
    def home_scene(sid,report=None):
        if report is not None:
            api.reports.append(report)
            return {'accepted':True}
        return dict(scene=api.scene, ready=api.ready, scene_id='scene-1', config_sha256='a'*64,
                    boot_id='boot-1', episode_id='ep-live',lease_id='lease-live')
    api.home_scene = home_scene
    provider = OpenAIAdapter('test-key','gpt-6-astra',camera_source=Cameras())
    controller = RunnerController(api,share_conversation=False)
    controller.join(provider,'move')
    api.get_session = lambda sid: dict(status='running',episode_id='ep-live',lease_id='lease-live',latest_observation_step=0)
    def fresh(robot):
        return {**api.scene['observation'], 'observed_at':time.time(), 'mode':'API_ACTIVE',
                'safety':{'ok':True,'estop_engaged':False}}
    api.get_robot_observation = fresh
    return controller,provider,api


def home(controller,api):
    controller._status = 'running'
    controller._episode_id='ep-live'
    controller._lease_id='lease-live'
    api.ready=True
    return {**api.get_robot_observation('yam-1'), 'episode_id':'ep-live','lease_id':'lease-live','step_id':0}


@pytest.mark.parametrize('mutate',[
    lambda s:s.update(captured_at=time.time()-121),
    lambda s:s.update(robot_id='other'),
    lambda s:s.update(config_sha256=None),
    lambda s:s['frames'].pop('top'),
    lambda s:s['frames']['top'].update(sha256='bad'),
    lambda s:s['frames']['top'].update(captured_at=time.time()-1),
    lambda s:s['observation'].update(settled=False),
    lambda s:s['observation'].update(left_gripper=None),
])
def test_invalid_scenes_never_start_a_model(mutate):
    c,p,a=setup();mutate(a.scene)
    with patch.object(p,'build_trajectory') as build:
        c._poll_home_scene()
    assert not build.called
    assert c._home_plan is None


def test_plan_overlaps_startup_and_waits_for_confirmed_home():
    c,p,a=setup()
    entered,release=threading.Event(),threading.Event()
    def model(payload):
        entered.set();assert release.wait(2)
        assert 'future starting state' in str(payload)
        return response('move_to',{'targets':{'left_z':.195},'note':'up'})
    with patch.object(p,'_post_json',side_effect=model):
        c._poll_home_scene();assert entered.wait(1)
        assert c._status=='queued' and a.action_log==[]
        release.set();assert c._home_plan.done.wait(2)
        assert a.action_log==[]
        points=c._take_home_plan(p,home(c,a))
    assert points and p._episode==('ep-live','lease-live')
    assert c._home_plan is None
    assert len([r for r in a.reports if 'first_executable_plan_s' in r])==1


def test_home_can_finish_before_model():
    c,p,a=setup();release=threading.Event()
    def model(payload):
        assert release.wait(2)
        return response('move_to',{'targets':{'left_z':.195},'note':'up'})
    with patch.object(p,'_post_json',side_effect=model):
        c._poll_home_scene();obs=home(c,a)
        results=[]
        waiter=threading.Thread(target=lambda:results.append(c._take_home_plan(p,obs)))
        waiter.start();assert not results and not a.action_log
        release.set();waiter.join(2)
    assert results[0]


@pytest.mark.parametrize('condition',['changed','timestamp','lease','gripper','config','not_ready','stale','steering'])
def test_bad_readiness_discards_entire_speculative_conversation(condition):
    c,p,a=setup()
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':{'left_z':.195},'note':'up'})):
        c._poll_home_scene();assert c._home_plan.done.wait(2)
    obs=home(c,a)
    if condition=='changed':p._camera_source.jpeg=b'\xff\xd8changed\xff\xd9'
    if condition=='timestamp':p._camera_source.timestamp=False
    if condition=='lease':a.get_session=lambda sid:dict(status='stopped')
    if condition=='gripper':a.scene['observation']['left_gripper']=.5
    if condition=='config':c._home_plan.scene=deepcopy(c._home_plan.scene);c._home_plan.scene['config_sha256']='b'*64
    if condition=='not_ready':a.ready=False
    if condition=='stale':c._home_plan.scene['captured_at']=time.time()-121
    if condition=='steering':p.steering.pending=lambda:True
    assert c._take_home_plan(p,obs) is None
    assert p._pending is None and not p._history and p._outcome is None
    assert not a.action_log


def test_cancel_joins_request_and_cannot_leak_into_next_run():
    c,p,a=setup();entered=threading.Event();exited=threading.Event()
    def model(payload):
        entered.set()
        while not p.cancelled():time.sleep(.005)
        exited.set();raise RuntimeError('cancelled')
    with patch.object(p,'_post_json',side_effect=model):
        c._poll_home_scene();job=c._home_plan
        assert entered.wait(1)
        c.stop()
        assert exited.is_set() and not job.thread.is_alive()
    assert not a.action_log
    # Teardown from an old worker must not cancel a new provider's worker.
    other=OpenAIAdapter('test-key','gpt-6-astra',camera_source=Cameras())
    c._home_plan=type('Job',(),{'provider':other,'close':lambda *a,**k:pytest.fail('wrong run cancelled')})()
    c._cancel_home_plan(p)


def test_failure_and_missing_cache_fall_back_without_reusing_partial_state():
    c,p,a=setup();a.scene=None
    c._poll_home_scene();assert c._home_plan is None
    a.scene=scene();c._home_next_poll=0
    with patch.object(p,'_post_json',side_effect=RuntimeError('offline')):
        c._poll_home_scene();assert c._home_plan.done.wait(2)
    assert c._take_home_plan(p,home(c,a)) is None
    assert not p._history


def test_profile_changes_with_model_speed_and_configuration():
    c,p,a=setup();before=profile_key(p)
    p.response_speed='standard';assert profile_key(p)!=before
    p.model='other';assert profile_key(p)!=before


def test_expired_validation_replans_before_any_packet_is_submitted():
    c,p,a=setup()
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':{'left_z':.195},'note':'up'})):
        c._poll_home_scene();assert c._home_plan.done.wait(2)
    obs=home(c,a);cached=c._take_home_plan(p,obs);assert cached
    c._home_validation_at=time.time()-3
    sent=[]
    class Submitted(Exception):pass
    def submit(*args):sent.append(args[-1]);raise Submitted()
    c._submit_attempts=1
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':{'left_z':.20},'note':'fresh'})), patch.object(p,'build_trajectory',wraps=p.build_trajectory) as rebuild, patch.object(a,'submit_trajectory',side_effect=submit):
        with pytest.raises(Submitted):
            c._dispatch_trajectory(lambda *_:cached,p,'move',obs,c._session_id,c._episode_id,c._lease_id,0)
    rebuild.assert_called_once()
    assert len(sent)==1 and sent[0]!=cached
    assert p._pending['waypoint_count']==len(sent[0])
    assert p._pending['targets']=={'left_z':.20}


def test_codex_discard_forgets_resume_and_orientation_reference():
    from remote_yam.codex_policy import CodexAdapter
    from test_codex_policy import decision,events
    with patch('remote_yam.codex_policy.codex_status',return_value={'ready':True}), patch('remote_yam.codex_policy.codex_binary',return_value='/no-cli'):
        p=CodexAdapter(camera_source=Cameras())
    try:
        move=decision('move_to',note='grip');move['targets']['left_gripper']=.9
        with patch.object(p,'_execute',return_value=events(move)):
            job=HomePlan(p,'move',scene(),'yam-1','s',lambda:False)
            assert job.done.wait(2)
        assert p._thread_id and p._pending and p._geometry.start_rotations is not None
        job.discard()
        assert p._thread_id is None and p._sent_items==0 and p._geometry.start_rotations is None
        assert not p._history and p._pending is None
    finally:p._workspace.cleanup()


@pytest.mark.parametrize('cached', [False, True])
def test_first_home_motion_rebuilds_recorded_target_from_current_joints(cached):
    from remote_yam.robocurve_trajectory import NAMES, MAX_JOINT_STEP_RAD
    c,p,a=setup()
    # ep_7471cd80b8fc4d54: Home settled while the first model call ran.
    a.scene['observation'].update(
        left_joints_deg=[-1.1912031676,45.582645981,35.375455536,-21.4744424245,-.6447796962,-.8633490848],
        right_joints_deg=[-1.2130601064,45.3859335313,35.0476014531,-21.6055840576,-1.1693462287,-.7759213293])
    target={'left_y':-.0606}
    sent=[]
    class Submitted(Exception):pass
    def submit(*args):
        sent.append(args[-1])
        raise Submitted()
    c._submit_attempts=1
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':target,'note':'toward duck'})) as model:
        if cached:
            c._poll_home_scene();assert c._home_plan.done.wait(2)
        obs=home(c,a)
        c._home_registered=True
        c._home_sample_recorded=True
        if cached:
            points=c._take_home_plan(p,obs);assert points
            builder=lambda *_:points
        else:
            builder=p.build_trajectory
        fresh=deepcopy(obs)
        fresh['right_joints_deg'][2]+=.54642347136
        a.get_robot_observation=lambda *_:{**fresh,'observed_at':time.time()}
        with patch.object(a,'submit_trajectory',side_effect=submit):
            with pytest.raises(Submitted):
                c._dispatch_trajectory(builder,p,'move',obs,c._session_id,c._episode_id,c._lease_id,0)
        assert model.call_count==1
    assert len(sent)==1
    points=sent[0]
    assert c._trajectory['start_feedback']['right_joints_deg']==fresh['right_joints_deg']
    assert c._trajectory['waypoint_count']==p._pending['waypoint_count']==len(points)
    assert p._pending['last_step_id']==points[-1]['step_id']
    previous=np.deg2rad(fresh['left_joints_deg']+fresh['right_joints_deg'])
    for point in points:
        current=np.deg2rad(point['left_joints_deg']+point['right_joints_deg'])
        assert np.max(np.abs(current-previous))<=MAX_JOINT_STEP_RAD+1e-12
        previous=current
    _,end,_=p._geometry.observe({**fresh,**points[-1]})
    assert abs(end[NAMES.index('left_y')]-target['left_y'])<3e-6
    p.trajectory_completed({**fresh,**points[-1],'step_id':len(points)},len(points))
    assert p._pending is None


def test_home_rebuild_preserves_tool_frame_and_updates_changed_packet_length():
    c,p,a=setup();obs=home(c,a)
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':{'right_y':.2},'note':'move'})) as model:
        old=p.build_trajectory('move',obs,0)
        rotations=tuple(r.copy() for r in p._geometry.start_rotations)
        history=deepcopy(p._history)
        fresh=deepcopy(obs);fresh['right_joints_deg'][2]+=.54642347136
        points=p.rebuild_pending_trajectory(fresh,0)
        assert model.call_count==1 and len(points)!=len(old)
    assert p._history==history
    for before,after in zip(rotations,p._geometry.start_rotations):
        np.testing.assert_array_equal(before,after)
    assert p._pending['waypoint_count']==len(points)
    p.trajectory_completed({**fresh,**points[-1],'step_id':len(points)},len(points))
    assert p._pending is None


@pytest.mark.parametrize('condition',['lease','not_homed','not_settled','fault','rebuild_error','stop'])
def test_home_rebuild_never_submits_without_valid_current_state(condition):
    from remote_yam.robocurve_trajectory import InvalidMove
    c,p,a=setup();obs=home(c,a);c._home_registered=True;c._home_sample_recorded=True
    fresh=deepcopy(obs)
    if condition=='lease':
        a.get_session=lambda *_:dict(status='running',episode_id='other',lease_id='other')
    if condition=='not_homed':fresh['homed']=False
    if condition=='not_settled':fresh['settled']=False
    if condition=='fault':fresh['safety']={'ok':False,'estop_engaged':False}
    a.get_robot_observation=lambda *_:fresh
    original=p.rebuild_pending_trajectory
    def rebuild(*args):
        if condition=='rebuild_error':raise InvalidMove('cannot rebuild','joint_pacing_limit')
        result=original(*args)
        if condition=='stop':c._stop_event.set()
        return result
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':{'left_z':.195},'note':'up'})), patch.object(p,'rebuild_pending_trajectory',side_effect=rebuild), patch.object(a,'submit_trajectory') as submit:
        if condition=='stop':
            c._dispatch_trajectory(p.build_trajectory,p,'move',obs,c._session_id,c._episode_id,c._lease_id,0)
        else:
            with pytest.raises((RuntimeError,InvalidMove)):
                c._dispatch_trajectory(p.build_trajectory,p,'move',obs,c._session_id,c._episode_id,c._lease_id,0)
        submit.assert_not_called()


@pytest.mark.parametrize('change',[{'episode_id':'other'},{'lease_id':'other'},{'step_id':1}])
def test_home_rebuild_rejects_wrong_pending_identity(change):
    c,p,a=setup();obs=home(c,a)
    with patch.object(p,'_post_json',return_value=response('move_to',{'targets':{'left_z':.195},'note':'up'})):
        p.build_trajectory('move',obs,0)
    pending=deepcopy(p._pending)
    with pytest.raises(RuntimeError,match='does not match'):
        p.rebuild_pending_trajectory({**obs,**change},change.get('step_id',0))
    assert p._pending==pending
