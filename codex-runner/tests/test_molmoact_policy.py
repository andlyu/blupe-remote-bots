import base64
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from remote_yam.molmoact_policy import MolmoActAdapter, VARIANT
from remote_yam.molmoact_protocol import identity, REVISION
from remote_yam.run_changes import snapshot
from remote_yam.session import MAX_COMMANDS


def adapter(mode='guided',strength=.15):
    camera=Mock()
    camera.capture_for_policy.return_value=[SimpleNamespace(name=n,jpeg=b'jpeg') for n in ('right','top','left')]
    p=MolmoActAdapter('private-key',camera_source=camera,endpoint='https://abc123.api.runpod.ai',mode=mode,strength=strength)
    p._ready.set()
    return p


def response(p):
    return dict(identity(),ok=True,device='cuda:0',cuda_available=True,
        actions=[[.1]*6+[.5]+[.2]*6+[.6] for _ in range(30)],
        experiment=dict(variant=VARIANT,mode=p.mode,effective_strength=p.strength,seed=0,
                        num_steps=10,revision=REVISION,dtype='bfloat16',enable_cuda_graph=False))


def observation():
    return dict(left_joints_deg=[10]*6,right_joints_deg=[20]*6,left_gripper=.4,right_gripper=.6)


def test_exact_schema_conversion_camera_roles_and_recorded_intervention():
    p=adapter();p._json=Mock(return_value=response(p))
    points=p.build_trajectory('Pick cup',observation(),0)
    payload=p._json.call_args.args[1]
    assert payload['robot_id']=='yam-1' and payload['mode']=='guided' and payload['guidance_strength']==.15
    assert set(payload['images'])=={'top','left','right'}
    assert payload['state'][0]==pytest.approx(.17453292519943295)
    assert len(points)>=10 and [x['step_id'] for x in points]==list(range(len(points)))
    assert points[-1]['left_joints_deg'][0]==pytest.approx(5.729577951)
    assert snapshot(p,'Pick cup',60)['guidance_strength']==.15
    assert 'private-key' not in str(p.public_config())


def test_rejects_bad_grippers_receipt_and_budget_without_clamping():
    p=adapter(); bad=observation();bad['left_gripper']=None
    p._json=Mock(return_value=response(p))
    with pytest.raises(ValueError):p.build_trajectory('Pick',bad,0)
    p._json.assert_not_called()
    value=response(p);value['actions'][0][6]=1.01;p._json.return_value=value
    with pytest.raises(ValueError):p.build_trajectory('Pick',observation(),0)
    value=response(p);value['experiment']['effective_strength']=.2;p._json.return_value=value
    with pytest.raises(ValueError):p.build_trajectory('Pick',observation(),0)
    p._json.return_value=response(p)
    with pytest.raises(ValueError):p.build_trajectory('Pick',observation(),MAX_COMMANDS-1)


def test_mismatched_robot_rejected_and_baseline_strength_is_zero():
    with pytest.raises(ValueError):MolmoActAdapter('key',camera_source=Mock(),endpoint='https://abc.api.runpod.ai',robot_id='robot-ba8413962083809c')
    assert adapter('baseline',.3).strength==0


def test_pacing_preserves_targets_and_bounds_all_joint_steps_from_measured_pose():
    import math
    from remote_yam.molmoact_policy import GATEWAY_JOINT_STEP_RAD
    p=adapter();state=[0.0]*6+[.2]+[0.0]*6+[.8]
    rows=[[.2]*6+[.6]+[-.3]*6+[.4] for _ in range(30)]
    points=p._gateway_trajectory(rows,state,7)
    previous=[0.0]*12
    for point in points:
        joints=point['left_joints_deg']+point['right_joints_deg']
        assert max(abs(math.radians(a-b)) for a,b in zip(joints,previous))<=GATEWAY_JOINT_STEP_RAD+1e-12
        assert 0<=point['left_gripper']<=1 and 0<=point['right_gripper']<=1
        previous=joints
    assert points[-1]['left_joints_deg']==[math.degrees(.2)]*6
    assert points[-1]['right_joints_deg']==[math.degrees(-.3)]*6
    assert points[-1]['left_gripper']==.6 and points[-1]['right_gripper']==.4
    assert snapshot(p,'task',60)['trajectory_pacing']['max_joint_step_rad']==GATEWAY_JOINT_STEP_RAD
    assert points[0]['step_id']==7


def test_pacing_rejects_complete_chunk_instead_of_truncating_or_clamping():
    p=adapter();state=[0.0]*14;rows=[[10.0]*6+[.5]+[0.0]*6+[.5] for _ in range(30)]
    with pytest.raises(ValueError,match='entire chunk rejected'):
        p._gateway_trajectory(rows,state,0)


def test_adapter_deadline_cancels_readiness_even_when_caller_only_checks_stop():
    policy=MolmoActAdapter('secret',camera_source=None,endpoint='https://abc.api.runpod.ai')
    policy.cancelled=lambda:True
    policy._warm_state='released'
    with pytest.raises(RuntimeError,match='cancelled'):
        policy.wait_ready(lambda:False)


def test_https_connection_is_reused_and_redirect_never_retried(monkeypatch):
    p=adapter();connection=Mock()
    reply=Mock(status=200);reply.read.return_value=b'{"ok":true}'
    connection.getresponse.return_value=reply
    factory=Mock(return_value=connection)
    monkeypatch.setattr('remote_yam.molmoact_policy.http.client.HTTPSConnection',factory)
    assert p._json('/health')=={'ok':True}
    assert p._json('/act',{'input':'test'})=={'ok':True}
    factory.assert_called_once_with('abc123.api.runpod.ai',timeout=30)
    assert connection.request.call_count==2
    reply.status=302
    with pytest.raises(RuntimeError,match='ValueError'):
        p._json('/act',{})
    assert connection.request.call_count==3
    connection.close.assert_called_once()
    assert p._connection is None
    assert 'private-key' not in str(p.public_config())


def test_prefetched_initial_camera_set_is_bound_to_fresh_leased_observation():
    import threading,time
    p=adapter();now=time.time();obs=dict(observation(),observed_at=now,images={})
    frames=[SimpleNamespace(name=n,jpeg=b'jpeg',source_captured_at=now) for n in ('right','top','left')]
    requested=threading.Event();release=threading.Event()
    def capture(*args,**kwargs):
        requested.set();assert release.wait(1);return frames
    p._camera_source.capture_for_policy.side_effect=capture
    p.prefetch_observation(obs)
    assert requested.wait(1) and not p._prefetch['done'].is_set()
    release.set()
    assert p._frames(obs)==frames
    assert p._camera_source.capture_for_policy.call_count==1
    assert p._prefetch is None


def test_stale_prefetch_is_discarded_and_cancel_blocks_model():
    import threading,time
    p=adapter();now=time.time();done=threading.Event();done.set()
    old=[SimpleNamespace(name=n,jpeg=b'old',source_captured_at=now-10) for n in ('right','top','left')]
    p._prefetch={'observed_at':now,'done':done,'frames':old}
    assert p._frames(dict(observation(),observed_at=now))==p._camera_source.capture_for_policy.return_value
    p._camera_source.capture_for_policy.assert_called_once()
    p.cancelled=lambda:True;p._json=Mock()
    with pytest.raises(RuntimeError,match='cancelled'):
        p.build_trajectory('Pick cup',observation(),0)
    p._json.assert_not_called()


def test_startup_boundaries_keep_first_native_home_and_admission_not_later_readiness():
    p=adapter();p.interaction_sink=Mock()
    p.note_queue({'session_id':'sess_one'})
    p.note_queue_snapshot({'entries':[{'session_id':'other','created_at':1}]})
    assert p.public_config()['startup_queue']['entered_at'] is None
    p.note_queue_snapshot({'entries':[{'session_id':'sess_one','created_at':10}]})
    p.note_queue_snapshot({'entries':[{'session_id':'sess_one','created_at':99}]})
    p.note_admission({'episode_id':'ep_one','timestamp':20},{})
    p.note_admission({'episode_id':'ep_one','timestamp':90},{})
    p.note_startup_home(dict(step_id=0,homed=True,settled=False,observed_at=21))
    assert p.public_config()['startup_home'] is None
    p.note_startup_home(dict(step_id=0,homed=True,settled=True,observed_at=22,episode_id='ep_one'))
    p.note_startup_home(dict(step_id=0,homed=True,settled=True,observed_at=99,episode_id='ep_one'))
    config=p.public_config()
    assert config['startup_queue']['entered_at']==10
    assert config['startup_queue']['admitted_at']==20
    assert config['startup_home']['completed_at']==22
    assert config['startup_home']['visually_verified'] is False
    assert 'private-key' not in str(config)


@pytest.mark.parametrize('available', [True,False,None])
def test_capacity_evidence_only_marks_proven_cold_launch(available):
    p=adapter();p._ready.clear()
    p._capacity_snapshot=Mock(return_value=dict(available=available,checked_at=1,workers=[]))
    p._json=Mock(return_value=dict(identity(),ok=True,device='cuda:0',cuda_available=True,variant=VARIANT,
        verification={k:True for k in ('pristine_baseline_equal','zero_strength_exact_equal','nonzero_text_kv_changed','non_goal_kv_unchanged')}))
    p._keep_ready(lambda:p._ready.is_set())
    gpu=p.public_config()['gpu_startup']
    assert gpu['launch_required'] is (None if available is None else not available)
    assert (gpu['launch_started_at'] is not None) is (available is False)
    assert gpu['ready_at'] is not None
