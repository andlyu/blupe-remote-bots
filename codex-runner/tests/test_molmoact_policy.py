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
    assert len(points)==10 and points[-1]['step_id']==9
    assert points[0]['left_joints_deg'][0]==pytest.approx(5.729577951)
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
