"""Real RoboSkills tools -> generator -> HTTP serializer/validator; no hardware."""
import importlib.util
import json
import math
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch
import numpy as np
from remote_yam.roboskills_policy import RoboSkillsPolicy, RobotTools
from remote_yam.session import HttpSessionAPI, _trajectory_waypoints
from remote_yam.robocurve_trajectory import NAMES
from test_roboskills_policy import Cameras, observation


@skipUnless(importlib.util.find_spec('roboskills'),'Install the pinned RoboSkills runtime')
class CommandContract(TestCase):
    def setUp(self):
        self.root=TemporaryDirectory()
        self.p=RoboSkillsPolicy(camera_source=Cameras(),recording_root=self.root.name,llm=lambda s,m:'')
        self.p._state=observation();self.p._identity=('ep_unit','lease_unit')
        self.bot=RobotTools(self.p,'offline contract')
        self.http=HttpSessionAPI('https://api.example')
        self.sent=[]

    def tearDown(self):self.root.cleanup()

    def plant(self, points):
        def transport(method,path,payload,**kwargs):
            # Actual JSON encoding/decoding after canonical packet validation.
            self.sent.append(json.loads(json.dumps(payload,allow_nan=False)))
            return {'accepted':True}
        with patch.object(self.http,'_request',side_effect=transport),patch.object(self.http,'_capability',return_value='offline'):
            self.http.submit_trajectory('offline','ep_unit','lease_unit','packet',10,points)
        return {**self.p._state,**points[-1],'settled':True,'step_id':points[-1]['step_id']+1}

    def test_both_grippers_endpoints_partial_and_fractional_starts(self):
        for arm in ('left','right'):
            for start,target in ((.9992793312193716,0.),(.00000000000001,1.),(.37,.62),(1.,0.),(0.,1.)):
                with self.subTest(arm=arm,start=start,target=target):
                    self.p._state=observation();self.p._state[arm+'_gripper']=start
                    before=self.p._state.copy();self.sent=[]
                    with patch.object(self.p,'_execute',side_effect=self.plant):self.bot.move_to(**{arm+'_gripper':target})
                    points=self.sent[-1]['waypoints'];other='right' if arm=='left' else 'left'
                    self.assertEqual(points[-1][arm+'_gripper'],target)
                    self.assertEqual([p['step_id'] for p in points],list(range(len(points))))
                    self.assertEqual(self.sent[-1]['cadence_hz'],10)
                    self.assertTrue(all(0<=p[arm+'_gripper']<=1 for p in points))
                    self.assertTrue(all(p[other+'_gripper']==before[other+'_gripper'] for p in points))
                    for p in points:
                        for side in ('left','right'):np.testing.assert_array_equal(p[side+'_joints_deg'],before[side+'_joints_deg'])
                    values=[start]+[p[arm+'_gripper'] for p in points]
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(values,values[1:])),.1+1e-12)

    def test_invalid_requested_values_never_reach_dispatch(self):
        for arm in ('left','right'):
            for value in (-1e-16,1+1e-15,-.1,1.1,float('nan'),float('inf'),True,'0',None):
                with self.subTest(arm=arm,value=value),patch.object(self.p,'_execute') as execute:
                    with self.assertRaises(ValueError):self.bot.move_to(**{arm+'_gripper':value})
                    execute.assert_not_called()

    def test_cartesian_both_arms_through_actual_serialization(self):
        for arm in ('left','right'):
            for axis,delta in (('x',.005),('y',.005),('z',.02),('yaw',.05)):
                with self.subTest(arm=arm,axis=axis):
                    self.p._state=observation();before=self.p._state.copy()
                    s=self.bot.status()['coordinates'];self.sent=[]
                    with patch.object(self.p,'_execute',side_effect=self.plant):self.bot.move_to(**{arm+'_'+axis:s[arm+'_'+axis]+delta})
                    packet=self.sent[-1]['waypoints'];other='right' if arm=='left' else 'left'
                    for point in packet:
                        np.testing.assert_array_equal(point[other+'_joints_deg'],before[other+'_joints_deg'])
                        for side in ('left','right'):self.assertEqual(point[side+'_gripper'],before[side+'_gripper'])
                    self.assertLess(self.p._last_move['position_error_m'][arm],.003)

    def test_cartesian_envelope_endpoints_and_invalid_neighbours(self):
        # A legal numeric endpoint can still be kinematically unreachable from
        # this pose; such requests must fail locally, rather than promise box reachability.
        for i,name in enumerate(NAMES):
            if name.endswith('gripper'):continue
            low,high=self.p._geometry.low[i],self.p._geometry.high[i]
            for target in (float(np.nextafter(low,-math.inf)),float(np.nextafter(high,math.inf)),float('nan'),float('inf')):
                with self.subTest(name=name,invalid=target),patch.object(self.p,'_execute') as execute:
                    with self.assertRaises(ValueError):self.bot.move_to(**{name:target})
                    execute.assert_not_called()
            for target in set((float(low),float(high),float(np.nextafter(low,high)),float(np.nextafter(high,low)))):
                self.p._state=observation()
                with self.subTest(name=name,endpoint=target),patch.object(self.p,'_execute',side_effect=self.plant) as execute:
                    try:self.bot.move_to(**{name:target})
                    except ValueError as exc:
                        self.assertIn(getattr(exc.__cause__,'code',None),('unreachable_target','joint_pacing_limit','packet_waypoint_budget'))
                        execute.assert_not_called()

    def test_malformed_generated_packet_is_actionable_without_dispatch(self):
        malformed=dict(step_id=0,left_joints_deg=[0.]*6,right_joints_deg=[0.]*6,left_gripper=-1.1102230246251565e-16)
        with patch.object(self.p._geometry,'build',return_value=[malformed]),patch.object(self.p,'_execute') as execute:
            with self.assertRaisesRegex(ValueError,'before dispatch.*left_gripper'):self.bot.move_to(left_gripper=0.)
            execute.assert_not_called()
            self.assertIsNone(self.bot.motion_failure)
            self.assertIsNone(self.bot.result)
        with self.assertRaises(ValueError):_trajectory_waypoints([malformed])
