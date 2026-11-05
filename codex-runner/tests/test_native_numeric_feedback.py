import json
import math

import numpy as np
import pytest

from test_controller_dream_executor import setup, finish
from test_dream_policy import observation
from remote_yam.dream_policy import state_input


def test_actual_workspace_repair_numeric_types_complete_without_false_abort():
    def repaired(op, payload):
        common={k:payload[k] for k in ['session_id','episode_id','lease_id','trajectory_id']}
        # Same construction as deployed yam_operator_hardware_web.py:699,711.
        left=list(tuple(np.rad2deg(np.deg2rad([1.]*6))))
        right=list(tuple(np.rad2deg(np.deg2rad([2.]*6))))
        assert type(left[0]) is np.float64
        assert json.loads(json.dumps(left)) == [1.]*6
        adjustment=dict(workspace_recovery='adjusted',changed_waypoints=1,
                        left_joints_deg=left,right_joints_deg=right,left_gripper=.3,right_gripper=.7)
        op.api_client.send(dict(common,type='trajectory_result',status='accepted',details=adjustment))
        op.api_client.send(dict(common,type='trajectory_progress',step_id=0))
        op.api_client.send(dict(common,type='observation',step_id=1,settled=True,
                               left_joints_deg=[1.]*6,right_joints_deg=[2.]*6))
        op.api_last_step=0
        op.api_client.send(dict(common,type='trajectory_result',status='completed'))
        return []
    _,executor,request,submitted,sent,adapters=setup(native_handler=repaired)
    executor.request(request)
    assert finish(executor)=='completed',executor.status()['failure']
    assert len(submitted)==1 and adapters[0].adjusted==1 and adapters[0].completed==1
    assert not any(p['type']=='safety_abort' for p in sent)


def test_native_measured_numpy_float64_has_the_same_meaning_as_wire_json():
    measured=observation()
    measured['left_joints_deg']=[np.float64(x) for x in measured['left_joints_deg']]
    measured['left_gripper']=np.float64(.3)
    actual=state_input(measured,'task')
    expected=state_input(json.loads(json.dumps(measured)),'task')
    assert actual==expected and type(actual['state.left_gripper'][0]) is float


@pytest.mark.parametrize('value',[True,float('nan'),float('inf'),'1.0',1j])
def test_native_measured_values_still_reject_non_real_or_non_finite(value):
    measured=dict(observation(),left_gripper=value)
    with pytest.raises(ValueError):state_input(measured,'task')
