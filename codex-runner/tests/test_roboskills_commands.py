"""Real RoboSkills tools -> generator -> HTTP serializer/validator; no hardware."""
import importlib.util
import json
import math
from tempfile import TemporaryDirectory
from pathlib import Path
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

    def test_recorded_home_cartesian_moves_align_selected_grasp_base_z_down(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/roboskills-home-attitude.json').read_text())['observation']
        for bind_workspace in (False,True):
            for index,arm in enumerate(('left','right')):
                with self.subTest(arm=arm,bind_workspace=bind_workspace):
                    self.p=RoboSkillsPolicy(camera_source=Cameras(),recording_root=self.root.name,llm=lambda s,m:'')
                    if bind_workspace:self.p.configure_robot_workspace('yam-1')
                    self.p._state=fixture.copy();self.p._identity=('ep_unit','lease_unit')
                    self.bot=RobotTools(self.p,'offline vertical grasp contract');self.sent=[]
                    with patch.object(self.p,'_execute',side_effect=self.plant):
                        self.bot.move_to(**{arm+'_x':.32,arm+'_y':-.20 if arm=='left' else .20,arm+'_z':.12},attitude='base_vertical')
                    _,rotation=self.p._geometry.ik._poses()[index]
                    np.testing.assert_allclose(rotation[:,2],[0,0,-1],atol=1e-5)
                    other=('right','left')[index]
                    previous=np.deg2rad(fixture[arm+'_joints_deg'])
                    for point in self.sent[0]['waypoints']:
                        np.testing.assert_array_equal(point[other+'_joints_deg'],fixture[other+'_joints_deg'])
                        current=np.deg2rad(point[arm+'_joints_deg'])
                        self.assertLessEqual(np.max(abs(current-previous)),.035+1e-10)
                        previous=current
                        for side in ('left','right'):self.assertEqual(point[side+'_gripper'],fixture[side+'_gripper'])
                    held=self.p._state.copy();self.sent=[]
                    with patch.object(self.p,'_execute',side_effect=self.plant):self.bot.move_to(**{arm+'_gripper':0.})
                    for point in self.sent[0]['waypoints']:
                        for side in ('left','right'):np.testing.assert_array_equal(point[side+'_joints_deg'],held[side+'_joints_deg'])
                    self.assertEqual(self.p._geometry.attitude_references[arm],'base_vertical')
                    self.assertEqual(self.p._geometry.attitude_references[other],'observed')

    def test_recorded_transfer_plan_compares_heights_without_dispatch_or_reference_change(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/roboskills-transfer-reach.json').read_text())
        self.p.configure_robot_workspace('yam-1')
        self.p._state=fixture['observation'].copy()
        self.bot.status()
        original=tuple(r.copy() for r in self.p._geometry.start_rotations)
        before=self.p._state.copy()
        for key,reachable in (('unreachable_target',False),('reachable_target',True)):
            with self.subTest(key=key),patch.object(self.p,'_execute') as execute:
                result=self.bot.plan_move(**fixture[key],attitude='base_vertical')
                self.assertEqual(result['reachable'],reachable)
                self.assertFalse(result['dispatched'])
                self.assertEqual(result['from_step_id'],before['step_id'])
                if reachable:self.assertGreater(result['waypoint_count'],0)
                else:self.assertEqual(result['code'],'unreachable_target')
                execute.assert_not_called()
                self.assertEqual(self.p._state,before)
                self.assertEqual(self.p._completed_moves,0)
                self.assertIsNone(self.p._local_rejection)
                self.assertEqual(self.p._geometry.attitude_references,{'left':'observed','right':'observed'})
                for a,b in zip(self.p._geometry.start_rotations,original):np.testing.assert_array_equal(a,b)
        # A station-constrained bound must survive the planning copy. The
        # recorded baseline is117.7deg; the low endpoint needs142.6deg here.
        original_high=self.p._geometry.ik.high.copy()
        self.p._geometry.ik.high[7]=math.radians(135)
        with patch.object(self.p,'_execute') as execute:
            constrained=self.bot.plan_move(**fixture['reachable_target'],attitude='base_vertical')
            self.assertFalse(constrained['reachable'])
            execute.assert_not_called()
        self.assertEqual(self.p._geometry.ik.high[7],math.radians(135))
        self.p._geometry.ik.high=original_high
        with patch.object(self.p,'_execute',side_effect=self.plant):
            self.bot.move_to(**fixture['reachable_target'],attitude='base_vertical')
        self.assertGreater(len(self.sent),0)
        self.assertLess(self.p._last_move['position_error_m']['right'],.003)
        for point in self.sent[-1]['waypoints']:
            np.testing.assert_array_equal(point['left_joints_deg'],before['left_joints_deg'])
            self.assertEqual(point['right_gripper'],before['right_gripper'])

    def test_local_plan_checks_canonical_packet_and_restores_uninitialized_reference(self):
        def malformed(points):
            points[-1]['right_gripper']=-1e-16
            return _trajectory_waypoints(points)
        with patch('remote_yam.roboskills_policy._trajectory_waypoints',side_effect=malformed),patch.object(self.p,'_execute') as execute:
            result=self.bot.plan_move(right_x=.32,right_y=.2,right_z=.12,attitude='base_vertical')
            self.assertFalse(result['reachable'])
            self.assertIn('right_gripper',result['reason'])
            execute.assert_not_called()
        self.assertIsNone(self.p._geometry.start_rotations)
        self.assertEqual(self.p._geometry.attitude_references,{'left':'observed','right':'observed'})
        self.assertIsNone(self.p._local_rejection)

    def test_local_plan_preserves_cancel_lease_and_motion_failure_guards(self):
        for field,value in (('lease_id','other'),('source','simulation'),('settled',False)):
            with self.subTest(field=field),patch.object(self.p,'_execute') as execute:
                self.p._state=observation()
                self.p._state[field]=value
                with self.assertRaises(RuntimeError):self.bot.plan_move(right_z=.12)
                execute.assert_not_called()
        self.p._state=observation()
        with patch.object(self.p,'_check_cancelled',side_effect=RuntimeError('cancelled')):
            with self.assertRaisesRegex(RuntimeError,'cancelled'):self.bot.plan_move(right_z=.12)
        self.bot.motion_failure='Physical move outcome uncertain'
        with self.assertRaisesRegex(RuntimeError,'uncertain'):self.bot.plan_move(right_z=.12)

    def test_invalid_alignment_is_zero_dispatch_and_preserves_reference(self):
        self.bot.status()
        original=tuple(r.copy() for r in self.p._geometry.start_rotations)
        for kwargs in ({'right_gripper':0.,'attitude':'base_vertical'},
                       {'right_z':.1,'attitude':'invalid'},
                       {'right_z':-1.,'attitude':'base_vertical'}):
            with self.subTest(kwargs=kwargs),patch.object(self.p,'_execute') as execute:
                with self.assertRaises(ValueError):self.bot.move_to(**kwargs)
                execute.assert_not_called()
                self.assertEqual(self.p._geometry.attitude_references,{'left':'observed','right':'observed'})
                for a,b in zip(self.p._geometry.start_rotations,original):np.testing.assert_array_equal(a,b)

    def test_canonical_rejection_rolls_back_prepared_attitude_without_dispatch(self):
        self.bot.status()
        original=tuple(r.copy() for r in self.p._geometry.start_rotations)
        real_build=self.p._geometry.build
        def malformed(*args,**kwargs):
            points=real_build(*args,**kwargs)
            points[-1]['right_gripper']=-1e-16
            return points
        with patch.object(self.p._geometry,'build',side_effect=malformed),patch.object(self.p,'_execute') as execute:
            with self.assertRaisesRegex(ValueError,'before dispatch.*right_gripper'):
                self.bot.move_to(right_x=.32,right_y=.2,right_z=.12,attitude='base_vertical')
            execute.assert_not_called()
        self.assertEqual(self.p._geometry.attitude_references,{'left':'observed','right':'observed'})
        for a,b in zip(self.p._geometry.start_rotations,original):np.testing.assert_array_equal(a,b)

    def test_observed_reference_remains_the_default_for_other_policies(self):
        from remote_yam.robocurve_trajectory import RoboCurveTrajectory
        fixture=json.loads((Path(__file__).parent/'fixtures/roboskills-home-attitude.json').read_text())['observation']
        geometry=RoboCurveTrajectory(preserve_uninstructed=True)
        _,state,_=geometry.observe(fixture);before=geometry.ik._poses()[1][1].copy()
        self.assertGreater(abs(before[0,2]),.8)
        points=geometry.build({'right_z':state[9]+.01},fixture,0)
        geometry.observe({**fixture,**points[-1],'settled':True})
        np.testing.assert_allclose(geometry.ik._poses()[1][1],before,atol=1e-4)

    def test_malformed_generated_packet_is_actionable_without_dispatch(self):
        malformed=dict(step_id=0,left_joints_deg=[0.]*6,right_joints_deg=[0.]*6,left_gripper=-1.1102230246251565e-16)
        with patch.object(self.p._geometry,'build',return_value=[malformed]),patch.object(self.p,'_execute') as execute:
            with self.assertRaisesRegex(ValueError,'before dispatch.*left_gripper'):self.bot.move_to(left_gripper=0.)
            execute.assert_not_called()
            self.assertIsNone(self.bot.motion_failure)
            self.assertIsNone(self.bot.result)
        with self.assertRaises(ValueError):_trajectory_waypoints([malformed])
