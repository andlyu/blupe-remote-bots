"""Real integrated MuJoCo state and common controller API, without rendering/I/O."""
import io
import json
import math
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(os.environ.get('GEMINI_TEST_RUNNER_ROOT', Path(__file__).resolve().parents[3]))
INTEGRATION = Path(__file__).resolve().parents[1]
SKILLS = Path(os.environ.get('GEMINI_SKILLS_ROOT','/opt/robotics/plugins/robotics/skills'))
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(INTEGRATION/'backend'))
from yam1_scene import Yam1Scene
from yam1_simulation import SimulatedDeviceLayer
from yam1_environment import Yam1Environment, LocalCommandRejected, RpcDeviceLayer
from yam_commands import YamCommands


class Yam1SimulationTests(unittest.TestCase):
    def setUp(self):
        c=json.loads((INTEGRATION/'tests/fixtures/yam1-calibration.json').read_text())
        self.scene=Yam1Scene(ROOT,INTEGRATION/'assets/linear4310',c)
        self.scene.set_configuration({'left':[.2,1.6,1.2,-.8,.1,-.2],
                                      'right':[-.2,1.5,1.3,-.9,-.1,.3]}, {'left':.9992793312193716,'right':.412345678})
        self.layer=SimulatedDeviceLayer(self.scene,ROOT,render_cameras=False)
        self.env=Yam1Environment(self.scene,self.layer,SKILLS)
        self.addCleanup(self.env.close)

    def test_same_controller_api_integrates_actual_state_and_exact_packets(self):
        initial=self.layer.data.qpos.copy()
        control_before=self.scene.data.qpos.copy()
        q=self.env.left.q_arm.copy();q[0]+=.02
        self.env.left.move_joint(q,duration_s=.5)
        self.assertGreaterEqual(float(self.layer.data.time),.5+.35)
        self.assertLess(float(self.layer.data.time),.5+.5)
        self.assertEqual(self.layer.cursor,5)
        self.assertFalse(np.array_equal(self.layer.data.qpos,initial))
        # FK data is not the integrated physics data and is never teleported
        # to a desired pose after stepping. Measurements come from physics.
        np.testing.assert_array_equal(self.scene.data.qpos,control_before)
        np.testing.assert_array_equal(self.env.left.q_arm,self.layer.data.qpos[self.scene.arm_qpos['left']])
        target=self.layer.packets[-1]['waypoints'][-1]
        self.assertAlmostEqual(math.radians(target['left_joints_deg'][0]),q[0],places=14)
        self.assertEqual([p['step_id'] for p in self.layer.packets[-1]['waypoints']],list(range(5)))

    def test_gripper_only_common_api_preserves_uninstructed_wire_state(self):
        before=self.layer.observation()
        self.env.right.set_gripper(0.,duration_s=.2)
        points=self.layer.packets[-1]['waypoints']
        self.assertEqual(points[-1]['right_gripper'],0.)
        for p in points:
            self.assertEqual(p['left_joints_deg'],before['left_joints_deg'])
            self.assertEqual(p['right_joints_deg'],before['right_joints_deg'])
            self.assertEqual(p['left_gripper'],before['left_gripper'])
        self.assertGreaterEqual(float(self.layer.data.time),.2+.35)
        self.assertLess(float(self.layer.data.time),.2+.5)

    def test_shared_compiler_packet_is_identical_before_physics_dispatch(self):
        before=self.layer.observation()
        command={'left/follower/goal_position/gripper':0.}
        expected=YamCommands(ROOT).compile(dict(commands=command,duration_s=.2),before,0)
        self.layer.apply(command,.2)
        self.assertEqual(self.layer.packets[-1]['waypoints'],expected)
        rpc=RpcDeviceLayer(io.StringIO(json.dumps(dict(kind='begin',observation=before))+'\n'),io.StringIO(),self.scene.safety)
        self.assertEqual(self.layer.commands_spec(),rpc.commands_spec())

    def test_invalid_requests_leave_simulation_cursor_time_and_state_unchanged(self):
        state=self.layer.data.qpos.copy();time=float(self.layer.data.time)
        for commands,duration in (({'left/follower/goal_position/gripper':-1e-16},1.),
                                  ({'right/follower/goal_position/joint1':float('nan')},1.),
                                  ({'unregistered':0.},1.),
                                  ({'left/follower/goal_position/gripper':0.},False)):
            with self.assertRaises(LocalCommandRejected) as error:self.layer.apply(commands,duration)
            self.assertFalse(error.exception.dispatched)
            self.assertEqual(self.layer.cursor,0);self.assertEqual(self.layer.data.time,time)
            self.assertFalse(self.layer.packets)
            np.testing.assert_array_equal(self.layer.data.qpos,state)

    def test_observe_and_end_do_not_advance_or_restart_physics(self):
        before=self.layer.data.qpos.copy();self.env.observe();self.env.close()
        np.testing.assert_array_equal(before,self.layer.data.qpos)
        self.assertEqual(self.layer.data.time,0.)
        with self.assertRaises(RuntimeError):self.layer.step({'left/follower/goal_position/gripper':0.})

    def test_no_load_partial_grip_hold_has_no_mapping_induced_drift(self):
        # Isolate command/readback mapping from contact or gravity hypotheses.
        # This numerical no-load check is not a physical gap/force certificate.
        self.scene.model.opt.gravity[:]=0
        self.scene.set_configuration({'left':[.2,1.6,1.2,-.8,.1,-.2],
                                      'right':[-.2,1.5,1.3,-.9,-.1,.3]}, {'left':.375,'right':.375})
        layer=SimulatedDeviceLayer(self.scene,ROOT,render_cameras=False)
        self.addCleanup(layer.end_stepping)
        result=layer.apply({'left/follower/goal_position/gripper':.375,
                            'right/follower/goal_position/gripper':.375},1.)
        for arm in ('left','right'):
            #1e-6 normalized =47.5nm per jaw; only numerical hold consistency.
            self.assertLess(abs(float(result[arm+'/follower/joint_position/gripper'])-.375),1e-6)

    def test_nominal_robot_gravity_hold_preserves_global_object_gravity(self):
        self.assertEqual(float(self.scene.model.opt.gravity[2]),-9.81)
        before=self.layer.data.qpos.copy()
        result=self.layer.apply({'left/follower/goal_position/gripper':.9992793312193716},1.)
        ids=[i for arm in ('left','right') for i in self.scene.arm_qpos[arm]]
        self.assertLess(float(np.max(np.abs(self.layer.data.qpos[ids]-before[ids]))),1e-7)
        self.assertIn('settled_at_sim_s',self.layer.packets[-1])


if __name__=='__main__':unittest.main()
