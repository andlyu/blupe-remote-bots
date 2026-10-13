import base64
from copy import deepcopy
import hashlib
import threading
import time
from unittest.mock import patch

import pytest

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
    fresh_points=[dict(step_id=0,left_joints_deg=obs['left_joints_deg'],right_joints_deg=obs['right_joints_deg'])]
    sent=[]
    class Submitted(Exception):pass
    def submit(*args):sent.append(args[-1]);raise Submitted()
    c._submit_attempts=1
    with patch.object(p,'build_trajectory',return_value=fresh_points) as rebuild, patch.object(a,'submit_trajectory',side_effect=submit):
        with pytest.raises(Submitted):
            c._dispatch_trajectory(lambda *_:cached,p,'move',obs,c._session_id,c._episode_id,c._lease_id,0)
    rebuild.assert_called_once()
    assert sent==[fresh_points]
    assert p._pending is None


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
