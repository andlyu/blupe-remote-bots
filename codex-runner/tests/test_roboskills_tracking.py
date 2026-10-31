"""Retained physical tracking residual -> synthetic regression, no hardware."""
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch
import numpy as np
from remote_yam.robocurve_trajectory import RoboCurveTrajectory
import test_roboskills_commands as contract
from test_roboskills_policy import observation


@skipUnless(importlib.util.find_spec('roboskills'),'Install the pinned RoboSkills runtime')
class TrackingTests(TestCase):
    setUp=contract.CommandContract.setUp
    tearDown=contract.CommandContract.tearDown
    plant=contract.CommandContract.plant

    def test_recorded_approach_residual_converges_within_original_bounds(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/roboskills-approach-tracking.json').read_text())
        self.p._geometry=RoboCurveTrajectory(base_spacing_m=.5,preserve_uninstructed=True)
        self.p._geometry.observe(fixture['reference']);self.p._state=fixture['start']
        goal=None;commands=[]
        samples=fixture['samples']
        def measured_plant(points):
            nonlocal goal
            # Validate/serialize the actual generated command before supplying
            # synthetic feedback interpolated from retained completed samples.
            wire_end=self.plant(points)
            _,cmd,_=self.p._geometry.observe(wire_end)
            if goal is None:goal=cmd[7:10].copy()
            offset=cmd[7:10]-goal;commands.append(offset)
            error=[]
            for axis in range(3):
                ordered=sorted((s['command_offset_m'][axis],s['measured_error_m'][axis]) for s in samples)
                error.append(np.interp(offset[axis],*[np.array(v) for v in zip(*ordered)]))
            xyz=goal+error
            synthetic=self.p._geometry.build(dict(zip(('right_x','right_y','right_z'),xyz.tolist())),self.p._state,self.p._state['step_id'])
            return {**wire_end,**{k:synthetic[-1][k] for k in ('left_joints_deg','right_joints_deg')},'settled':True}
        with patch.object(self.p,'_execute',side_effect=measured_plant):
            self.bot.move_to(**fixture['targets'])
        self.assertLessEqual(len(commands),4)
        self.assertLessEqual(np.max(np.abs(commands)),.008+1e-7)
        self.assertLessEqual(self.p._last_move['position_error_m']['right'],.003)
        self.assertIsNone(self.bot.motion_failure)

    def test_gripper_only_command_reports_pose_drift_without_inventing_a_pose_target(self):
        before=observation();self.p._state=before
        pose=self.bot.status()['coordinates']
        def measured(points):
            end=self.plant(points)
            drift=self.p._geometry.build({'right_z':pose['right_z']+.005},before,0)[-1]
            return {**end,'right_joints_deg':drift['right_joints_deg']}
        with patch.object(self.p,'_execute',side_effect=measured) as execute:
            result=self.bot.move_to(right_gripper=0.)
        execute.assert_called_once()
        self.assertGreater(self.p._last_move['position_error_m']['right'],.004)
        self.assertEqual(self.p._last_move['pose_target_arms'],[])
        self.assertIn('coordinates',result)
        for waypoint in self.sent[0]['waypoints']:
            for side in ('left','right'):self.assertEqual(waypoint[side+'_joints_deg'],before[side+'_joints_deg'])
