"""Container RPC facade, exact gripper-only requests and matching feedback."""
import io
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from yam1_environment import RpcDeviceLayer, Arm, LocalCommandRejected


def feedback(**extra):
    return dict(source='simulation', observed_at=1., settled=True,
                left_joints_deg=[1., 90., 60., -20., 3., 5.],
                right_joints_deg=[2., 80., 70., -30., 4., 6.],
                left_gripper=.9992793312193716, right_gripper=.412345678, **extra)


class Environment:
    def __init__(self, layer): self.device_layer=layer;self._measurements=layer.begin_stepping()
    @property
    def measurements(self):return self._measurements


class Yam1EnvironmentTests(unittest.TestCase):
    def test_gripper_only_preserves_joint_fields_and_exact_endpoints(self):
        for arm in ('left','right'):
            for target in (0.,1.,.375):
                start=feedback();end=dict(start);end[arm+'_gripper']=target
                source=io.StringIO(json.dumps(dict(kind='begin',observation=start))+'\n'+
                                   json.dumps(dict(kind='completed',request_id=0,observation=end))+'\n')
                sink=io.StringIO();layer=RpcDeviceLayer(source,sink,{})
                env=Environment(layer);a=Arm(env,arm)
                before=a.q_arm.copy();a.set_gripper(target)
                message=json.loads(sink.getvalue())
                self.assertEqual(message['payload']['commands'],{arm+'/follower/goal_position/gripper':target})
                self.assertEqual(a.gripper,target)
                self.assertEqual(a.q_arm.tolist(),before.tolist())

    def test_local_rejection_updates_measured_state_without_hidden_resubmission(self):
        value=feedback();fresh=dict(value,left_gripper=.6)
        inputs=[dict(kind='begin',observation=value),
                dict(kind='rejected',request_id=0,dispatched=False,message='strict local range rejection'),
                dict(kind='observation',request_id=0,observation=fresh)]
        source=io.StringIO(''.join(json.dumps(v)+'\n' for v in inputs));sink=io.StringIO()
        layer=RpcDeviceLayer(source,sink,{})
        with self.assertRaises(LocalCommandRejected) as error:layer.apply({'left/follower/goal_position/gripper':-1e-16},1.)
        self.assertFalse(error.exception.dispatched)
        self.assertEqual(layer.begin_stepping()['left/follower/joint_position/gripper'],.6)
        self.assertEqual(len(sink.getvalue().splitlines()),1)

    def test_invalid_primitive_inputs_are_not_written_to_channel(self):
        source=io.StringIO(json.dumps(dict(kind='begin',observation=feedback()))+'\n');sink=io.StringIO()
        env=Environment(RpcDeviceLayer(source,sink,{}));a=Arm(env,'left')
        for value in (-1e-16,1+1e-15,float('nan'),float('inf'),True):
            with self.assertRaises(LocalCommandRejected):a.set_gripper(value)
        for q in ([0]*5,[False]*6,[float('nan')]*6):
            with self.assertRaises(LocalCommandRejected):a.move_joint(q)
        self.assertEqual(sink.getvalue(),'')

    def test_wrong_completion_identity_or_unknown_outcome_does_not_replay(self):
        for extra in (dict(kind='completed',request_id=1,observation=feedback()),
                      dict(kind='unknown',request_id=0)):
            source=io.StringIO(json.dumps(dict(kind='begin',observation=feedback()))+'\n'+json.dumps(extra)+'\n');sink=io.StringIO()
            layer=RpcDeviceLayer(source,sink,{})
            with self.assertRaises(RuntimeError):layer.apply({'left/follower/goal_position/gripper':0},1.)
            self.assertEqual(len(sink.getvalue().splitlines()),1)


if __name__ == '__main__': unittest.main()
