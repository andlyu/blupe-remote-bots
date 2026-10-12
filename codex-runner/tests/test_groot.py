import io
import math
from pathlib import Path
import sys
import threading
from unittest.mock import patch
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from remote_yam.groot_policy import GrootAdapter, MODEL
from remote_yam.controller import RunnerController
from remote_yam.session import MockSessionAPI
from remote_yam.cameras import CameraFrame


def test_warmup_begins_only_after_queue_acceptance_and_stops_on_leave():
    api=MockSessionAPI(auto_activate=False)
    class Policy:
        provider_name='groot'
        def public_config(self): return {'provider':'groot','model':MODEL}
        def start_preparation(self,cancelled):
            assert any(x['status']=='queued' for x in api.get_queue_snapshot()['entries'])
            self.cancelled=cancelled
    p=Policy();c=RunnerController(api);c.join_and_run(p,'bin')
    assert not p.cancelled() and not api.action_log
    c.stop();assert p.cancelled()
    c._worker.join(1)


def test_rejected_queue_does_not_start_gpu():
    class Reject(MockSessionAPI):
        def create_session(self,*args,**kwargs): raise RuntimeError('full')
    p=GrootAdapter('secret',camera_source=None)
    with pytest.raises(RuntimeError): RunnerController(Reject()).join_and_run(p,'bin')
    assert p._thread is None


def test_wait_cancelled_and_public_config_never_exposes_key():
    p=GrootAdapter('private-secret',camera_source=None)
    with pytest.raises(RuntimeError,match='cancelled'): p.wait_ready(lambda:True)
    assert 'private-secret' not in str(p.public_config())


def test_configured_checkpoint_routes_exact_identity_and_hides_endpoint():
    p, observation = policy_and_observation()
    model = 'groot-northstar-purple-crate-step10000'
    p = GrootAdapter('private-secret', camera_source=p._camera_source, model=model,
                     endpoint='https://testendpoint.api.runpod.ai',
                     norm_tag='yam_northstar_purple_crate', artifact_sha256='a' * 64)
    p._ready.set()
    seen = []
    def send(path, payload):
        seen.append(payload)
        return {'model': model, 'checkpoint_step': 10000, 'action_units': 'radians',
                'actions': [[0] * 6 + [.2] + [0] * 6 + [.8]] * 30}
    p._json = send
    assert len(p.build_trajectory('Place the cubes into the purple crate', observation, 0)) == 10
    assert seen[0]['model'] == model
    assert p.public_config()['model'] == model
    assert 'testendpoint' not in str(p.public_config())
    with pytest.raises(ValueError, match='RunPod'):
        GrootAdapter('private-secret', camera_source=None, endpoint='https://example.com')


def test_wrong_artifact_cannot_finish_warmup():
    p = GrootAdapter('secret', camera_source=None, artifact_sha256='a' * 64)
    p._json = lambda path: {'ok': True, 'cuda_available': True, 'device': 'cuda:0',
        'checkpoint_step': 10000, 'action_dim': 14, 'num_actions': 30,
        'norm_tag': 'yam_reviewed_groot', 'available_models': [MODEL], 'artifact_sha256': 'b' * 64}
    with patch('remote_yam.groot_policy.time.monotonic', side_effect=[0, 601]):
        p._keep_ready(lambda: False)
    assert not p._ready.is_set()
    assert p._warm_state == 'failed'


def policy_and_observation():
    b=io.BytesIO();Image.new('RGB',(640,360)).save(b,format='JPEG')
    class Cameras:
        def capture_for_policy(self,*a,**kw):return [CameraFrame(n,b.getvalue(),0) for n in ('left','top','right')]
    p=GrootAdapter('private-secret',camera_source=Cameras());p._ready.set()
    o={'left_joints_deg':[0]*6,'right_joints_deg':[0]*6,'left_gripper':.2,'right_gripper':.8}
    return p,o


def test_model_state_units_chunk_validation_and_gateway_sampling():
    p,o=policy_and_observation();seen=[]
    row=[0]*6+[.3]+[0]*6+[.7]
    row[0]=.005;row[7]=-.005
    def send(path,payload):
        seen.append(payload)
        return {'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row[:] for _ in range(30)]}
    p._json=send
    points=p.build_trajectory('bin',o,10)
    assert seen[0]['state']==[0]*6+[.2]+[0]*6+[.8]
    assert set(seen[0]['images'])=={'top_cam','left_cam','right_cam'}
    assert points[0]['step_id']==10 and len(points)==10
    assert points[-1]['left_joints_deg'][0]==pytest.approx(math.degrees(.005))
    assert points[-1]['right_joints_deg'][0]==pytest.approx(math.degrees(-.005))
    assert points[-1]['left_gripper']==.3
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row]*29}
    with pytest.raises(ValueError,match='chunk'):p.build_trajectory('bin',o,0)


def test_chunk_keeps_one_second_and_gripper_alignment():
    p,o=policy_and_observation()
    rows=[]
    for i in range(30):
        rows.append([.001*(i+1)]+[0]*5+[i/30]+[-.001*(i+1)]+[0]*5+[1-i/30])
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':rows}
    points=p.build_trajectory('bin',o,0)
    assert len(points)/10 == 1
    for point,row in zip(points,rows[2::3]):
        assert point['left_joints_deg'][0] == pytest.approx(math.degrees(row[0]))
        assert point['right_joints_deg'][0] == pytest.approx(math.degrees(row[7]))
        assert point['left_gripper'] == row[6]
        assert point['right_gripper'] == row[13]


@pytest.mark.parametrize('index',[2,29])
@pytest.mark.parametrize('joint',[0,1,2,3,4,5,7,8,9,10,11,12])
def test_large_joint_changes_keep_targets_and_duration_for_gateway_validation(index,joint):
    p,o=policy_and_observation()
    events=[]
    p.interaction_sink=lambda kind,message,**details:events.append((kind,details))
    rows=[[0]*6+[.2]+[0]*6+[.8] for _ in range(30)]
    rows[index][joint]=.06483
    rows[index][6]=.8
    rows[index][13]=.2
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':rows}
    points=p.build_trajectory('bin',o,10)
    assert len(points)==10
    for offset,(point,row) in enumerate(zip(points,rows[2::3])):
        assert point['step_id']==10+offset
        assert point['left_joints_deg']==pytest.approx([math.degrees(v) for v in row[:6]])
        assert point['right_joints_deg']==pytest.approx([math.degrees(v) for v in row[7:13]])
        assert point['left_gripper']==row[6]
        assert point['right_gripper']==row[13]
    assert not events


@pytest.mark.parametrize('jump',[.010001,.06483,-.06483,.301])
def test_runner_does_not_impose_a_joint_delta_cutoff(jump):
    p,o=policy_and_observation()
    row=[jump]+[0]*5+[.2]+[0]*6+[.8]
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row]*30}
    points=p.build_trajectory('bin',o,0)
    assert len(points)==10
    assert all(point['left_joints_deg'][0]==pytest.approx(math.degrees(jump)) for point in points)


def test_degree_conversion_overflow_is_rejected_before_dispatch():
    p,o=policy_and_observation()
    row=[1e308]+[0]*5+[.2]+[0]*6+[.8]
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row]*30}
    with pytest.raises(ValueError,match='finite gateway angles'):
        p.build_trajectory('bin',o,0)


def test_gateway_rejection_stops_groot_without_retrying_or_slowing():
    import time
    class RejectingGateway(MockSessionAPI):
        def submit_trajectory(self, session_id, episode_id, lease_id, trajectory_id, cadence_hz, waypoints):
            self.trajectory_attempts.append({'cadence_hz':cadence_hz,'waypoints':waypoints})
            self._event(self._record(session_id), 'trajectory_result', {
                'episode_id':episode_id,'lease_id':lease_id,'trajectory_id':trajectory_id,
                'status':'rejected','reported_at':time.time(),'code':'joint_velocity_limit',
                'message':'Configured joint velocity limit exceeded'})
            return {'schema_version':1,'accepted':True,'duplicate':False,
                'session_id':session_id,'episode_id':episode_id,'lease_id':lease_id,
                'trajectory_id':trajectory_id,'first_step_id':waypoints[0]['step_id'],
                'last_step_id':waypoints[-1]['step_id'],'waypoint_count':len(waypoints),
                'dispatched_at':time.time()}
    p,o=policy_and_observation()
    row=[.06483]+[0]*5+[.2]+[0]*6+[.8]
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row]*30}
    p.start_preparation=lambda cancelled:None
    api=RejectingGateway(observations=[o]);controller=RunnerController(api)
    controller.update_monitor_observation(api.get_robot_observation('yam-1'))
    controller.join(p,'Place the cubes into the purple crate')
    controller._run_loop(None)
    assert 'joint_velocity_limit' in controller.status()['error']
    assert len(api.trajectory_attempts)==1 and not api.action_log
    packet=api.trajectory_attempts[0]
    assert packet['cadence_hz']==10 and len(packet['waypoints'])==10
    assert packet['waypoints'][0]['left_joints_deg'][0]==pytest.approx(math.degrees(.06483))


def test_full_chunk_fits_remaining_session_budget_without_slowdown():
    p,o=policy_and_observation()
    row=[.06483]+[0]*5+[.2]+[-.06483]+[0]*5+[.8]
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row]*30}
    points=p.build_trajectory('bin',o,2990)
    assert len(points)==10 and points[-1]['step_id']==2999
    assert points[0]['left_joints_deg'][0]==pytest.approx(math.degrees(.06483))
    assert points[0]['right_joints_deg'][0]==pytest.approx(math.degrees(-.06483))
    with pytest.raises(ValueError,match='gateway budget'):
        p.build_trajectory('bin',o,2991)


def test_cancellation_during_chunk_build_returns_no_partial_trajectory():
    p,o=policy_and_observation()
    row=[.005]+[0]*5+[.2]+[0]*6+[.8]
    p._json=lambda *a:{'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[row]*30}
    calls=0
    def cancelled():
        nonlocal calls
        calls+=1
        return calls>=5
    p.cancelled=cancelled
    with pytest.raises(RuntimeError,match='cancelled'):
        p.build_trajectory('bin',o,0)


def test_late_inference_after_stop_cannot_return_commands():
    p,o=policy_and_observation();stopped=False
    def send(*args):
        nonlocal stopped
        stopped=True
        return {'model':MODEL,'checkpoint_step':10000,'action_units':'radians','actions':[[0]*14 for _ in range(30)]}
    p._json=send;p.cancelled=lambda:stopped
    with pytest.raises(RuntimeError,match='cancelled'):p.build_trajectory('bin',o,0)


@pytest.mark.parametrize('change', [
    {'lease_id':'replacement'}, {'status':'stopped'},
    {'latest_observation_step':1}, {'active_trajectory':{'trajectory_id':'other'}},
])
def test_cold_start_revalidates_lease_and_step_before_reading_or_acting(change):
    from types import SimpleNamespace
    class Policy:
        def wait_ready(self,cancelled): return True
    live={'status':'running','episode_id':'episode','lease_id':'lease',
          'latest_observation_step':0,'active_trajectory':None,**change}
    def unexpected(*args): raise AssertionError('Must reject before fresh camera/robot access')
    api=SimpleNamespace(get_session=lambda sid:live,get_robot_observation=unexpected)
    c=RunnerController(api);c._provider=Policy();c._status='running';c._session_id='session'
    c._episode_id='episode';c._lease_id='lease'
    with pytest.raises(RuntimeError,match='Session changed'):
        c._observation({}, {'step_id':0,'episode_id':'episode','lease_id':'lease'})


def test_cold_start_uses_fresh_feedback_with_same_lease():
    from types import SimpleNamespace
    import time
    seen=[]
    class ReachedInference(Exception): pass
    class Policy:
        def wait_ready(self,cancelled): return True
        def infer(self,prompt,observation):
            seen.append(observation);raise ReachedInference()
    live={'status':'running','episode_id':'episode','lease_id':'lease',
          'latest_observation_step':0,'active_trajectory':None}
    fresh={'source':'simulation','observed_at':time.time(),'left_joints_deg':[1]*6,
           'right_joints_deg':[2]*6,'left_gripper':.2,'right_gripper':.8,'settled':True,'homed':True}
    api=SimpleNamespace(get_session=lambda sid:live,get_robot_observation=lambda rid:fresh)
    c=RunnerController(api);c._provider=Policy();c._status='running';c._session_id='session'
    c._episode_id='episode';c._lease_id='lease'
    with pytest.raises(ReachedInference):
        c._observation({}, {'step_id':0,'episode_id':'episode','lease_id':'lease','observed_at':0,
                            'left_joints_deg':[0]*6,'right_joints_deg':[0]*6})
    assert seen[0]['left_joints_deg']==[1]*6
    assert seen[0]['observed_at']==fresh['observed_at']


@pytest.mark.parametrize('changed', [{'settled':False}, {'homed':False}])
def test_cold_start_rejects_hardware_that_lost_readiness(changed):
    from types import SimpleNamespace
    import time
    class Policy:
        def wait_ready(self, cancelled): return True
        def infer(self, *args): raise AssertionError('Unready hardware must not reach inference')
    live = {'status':'running', 'episode_id':'episode', 'lease_id':'lease',
            'latest_observation_step':0, 'active_trajectory':None}
    original = {'source':'hardware', 'step_id':0, 'episode_id':'episode', 'lease_id':'lease',
                'left_joints_deg':[0]*6, 'right_joints_deg':[0]*6,
                'left_gripper':.5, 'right_gripper':.5, 'settled':True, 'homed':True,
                'observed_at':time.time(), 'mode':'API_ACTIVE',
                'safety':{'ok':True, 'estop_engaged':False}}
    fresh = {**original, **changed}
    api = SimpleNamespace(get_session=lambda sid:live, get_robot_observation=lambda rid:fresh)
    controller = RunnerController(api)
    controller._provider = Policy()
    controller._status = 'running'
    controller._session_id = 'session'
    controller._episode_id = 'episode'
    controller._lease_id = 'lease'
    with pytest.raises(RuntimeError, match='Hardware feedback blocked: completion_not_explicitly_'):
        controller._observation({}, original)
