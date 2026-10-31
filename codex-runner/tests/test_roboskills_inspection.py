"""Noncontact camera inspection through the native serializer; never hardware."""
from copy import deepcopy
import json
import importlib.util
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch
import numpy as np
import test_roboskills_orientation as orientation
FIXTURE=orientation.FIXTURE

RETREAT=json.loads((Path(__file__).parent/'fixtures/roboskills-inspection-retreat.json').read_text())

@skipUnless(importlib.util.find_spec('roboskills'),'Install the pinned RoboSkills runtime')
class InspectionTests(TestCase):
    # Reuse setup and the actual canonical HTTP serialization plant, without
    # inheriting the orientation test inventory in this new test class.
    setUp=orientation.OrientationContract.setUp
    tearDown=orientation.OrientationContract.tearDown
    setUpGeometry=orientation.OrientationContract.setUpGeometry
    plant=orientation.OrientationContract.plant
    def test_compact_first_inspection_retains_source_candidate_and_fresh_images(self):
        for arm in ('left','right'):
            with self.subTest(arm=arm):
                self.setUpGeometry();self.sent=[]
                source={'points_base_m':deepcopy(FIXTURE['sourcePoints']),'camera':'top','pixel':[310,83]}
                images={'top':np.zeros((2,2,3),dtype=np.uint8)}
                with patch.object(self.bot,'measure_depth',return_value=source),patch.object(self.p,'_execute',side_effect=self.plant),patch.object(self.bot,'observe',return_value=images) as observe:
                    result=self.bot.inspect_source(310,83,arm=arm)
                self.assertIs(result,images);observe.assert_called_once()
                reference=self.bot.status()['inspection_reference']
                self.assertEqual(reference['source'],source)
                self.assertEqual(reference['candidate']['arm'],arm)
                self.assertEqual(reference['step_id'],self.p._state['step_id'])
                self.assertLessEqual(self.p._last_move['position_error_m'][arm],.003)
                self.assertEqual(self.p._last_move['goal'],'exact_pose')
                self.assertTrue(self.sent)

    def recorded_start(self):
        self.p._state=deepcopy(RETREAT['start']);self.bot.status()
        # The recorded approach already completed within the unchanged exact
        # pose limits. This is the new helper's explicit precontact provenance.
        self.bot._inspection_reference={'source':{'points_base_m':RETREAT['source_points']},
            'candidate':{'arm':'left'},'step_id':self.p._state['step_id']}

    def test_recorded_first_retreat_reaches_view_region_and_observes_actual_pose(self):
        self.recorded_start()
        def measured(points):
            end=self.plant(points)
            return {**end,**{k:v for k,v in RETREAT['first_completed'].items() if k.endswith(('joints_deg','gripper'))}}
        with patch.object(self.p,'_execute',side_effect=measured) as execute,patch.object(self.bot,'observe',return_value={'actual':'images'}) as observe:
            result=self.bot.retreat_for_view(.04)
        execute.assert_called_once();observe.assert_called_once()
        self.assertEqual(result,{'actual':'images'})
        self.assertIsNone(self.bot.motion_failure)
        self.assertGreater(self.p._last_move['position_error_m']['left'],.003)
        self.assertLess(self.p._last_move['position_error_m']['left'],.006)
        self.assertEqual(self.p._last_move['goal'],'noncontact_view_region')
        self.assertEqual(self.p._last_move['position_tolerance_m'],.006)
        self.assertIsNone(self.bot.status()['inspection_reference'])
        self.assertEqual(self.p._last_move['measured_coordinates'],self.bot.status()['coordinates'])

    def test_same_recorded_residual_still_fails_an_exact_move(self):
        self.recorded_start()
        def measured(points):
            end=self.plant(points)
            return {**end,**{k:v for k,v in RETREAT['first_completed'].items() if k.endswith(('joints_deg','gripper'))}}
        with patch.object(self.p,'_execute',side_effect=measured),self.assertRaisesRegex(RuntimeError,'within3mm'):
            self.bot.move_to(**RETREAT['nominal_targets'])
        self.assertIsNotNone(self.bot.motion_failure)

    def test_retreat_preconditions_and_numeric_bounds_reject_before_dispatch(self):
        for distance in (0,.0199999,.0500001,-.04,np.nan,np.inf,True,'0.04',None):
            self.recorded_start()
            with self.subTest(distance=distance),patch.object(self.p,'_execute') as execute:
                with self.assertRaises(ValueError):self.bot.retreat_for_view(distance)
                execute.assert_not_called()
        for change in ('no_reference','cursor','closed','low','uncertain','stop','lease','not_settled'):
            self.recorded_start()
            if change=='no_reference':self.bot._inspection_reference=None
            if change=='cursor':self.bot._inspection_reference['step_id']-=1
            if change=='closed':self.p._state['left_gripper']=.5
            if change=='low':self.bot._inspection_reference['source']['points_base_m']= {'left':[0,0,1.]}
            if change=='uncertain':self.bot.motion_failure='Physical move outcome uncertain'
            if change=='lease':self.p._state['lease_id']='other'
            if change=='not_settled':self.p._state['settled']=False
            with self.subTest(change=change),patch.object(self.p,'_execute') as execute:
                context=patch.object(self.p,'_check_cancelled',side_effect=RuntimeError('Stop')) if change=='stop' else patch.object(self.p,'_interaction')
                with context,self.assertRaises((ValueError,RuntimeError)):self.bot.retreat_for_view(.04)
                execute.assert_not_called()
            self.bot.motion_failure=None

    def test_retreat_both_endpoint_distances_preserve_other_arm_and_grippers(self):
        for arm in ('left','right'):
            for distance in (.02,.035,.05):
                with self.subTest(arm=arm,distance=distance):
                    self.setUpGeometry();self.sent=[]
                    source={'points_base_m':deepcopy(FIXTURE['sourcePoints'])}
                    with patch.object(self.bot,'measure_depth',return_value=source),patch.object(self.p,'_execute',side_effect=self.plant),patch.object(self.bot,'observe'):
                        self.bot.inspect_source(310,83,arm=arm)
                    before=deepcopy(self.p._state);start=self.bot.status()['coordinates'];self.sent=[]
                    with patch.object(self.p,'_execute',side_effect=self.plant),patch.object(self.bot,'observe'):
                        self.bot.retreat_for_view(distance)
                    self.assertGreater(self.bot.status()['coordinates'][arm+'_z'],start[arm+'_z'])
                    other='right' if arm=='left' else 'left'
                    for packet in self.sent:
                        ids=[w['step_id'] for w in packet['waypoints']]
                        self.assertEqual(ids,list(range(before['step_id'],before['step_id']+len(ids))))
                        for w in packet['waypoints']:
                            self.assertEqual(w[other+'_joints_deg'],before[other+'_joints_deg'])
                            for side in ('left','right'):self.assertEqual(w[side+'_gripper'],before[side+'_gripper'])

    def test_failed_retreat_never_observes_or_dispatches_again(self):
        self.recorded_start()
        with patch.object(self.p,'_execute',side_effect=TimeoutError('unknown execution')) as execute,patch.object(self.bot,'observe') as observe:
            with self.assertRaises(TimeoutError):self.bot.retreat_for_view(.04)
            with self.assertRaises(RuntimeError):self.bot.retreat_for_view(.04)
        execute.assert_called_once();observe.assert_not_called()

    def test_view_region_inside_outside_and_orientation_limits(self):
        for residual,angle,accepted in ((.00599,0,True),(.00601,0,False),(.001,2.1,False)):
            with self.subTest(residual=residual,angle=angle):
                self.recorded_start();self.bot.motion_failure=None;self.bot.result=None;self.sent=[]
                nominal=None
                def measured(points):
                    nonlocal nominal
                    end=self.plant(points)
                    _,current,_=self.p._geometry.observe(end)
                    if nominal is None:nominal=current[:3].copy()
                    goal=nominal+np.array([0,0,-residual])
                    # Explicit synthetic post-completion plant, not a claim
                    # about real controller responses near the boundary.
                    target=dict(zip(('left_x','left_y','left_z'),goal.tolist()))
                    if angle:target['left_yaw']=current[3]+np.deg2rad(angle)
                    synthetic=self.p._geometry.build(target,end,end['step_id'])[-1]
                    return {**end,'left_joints_deg':synthetic['left_joints_deg']}
                with patch.object(self.p,'_execute',side_effect=measured) as execute,patch.object(self.bot,'observe') as observe:
                    if accepted:
                        self.bot.retreat_for_view(.04);observe.assert_called_once();execute.assert_called_once()
                    else:
                        with self.assertRaisesRegex(RuntimeError,'within6mm'):self.bot.retreat_for_view(.04)
                        observe.assert_not_called();self.assertLessEqual(execute.call_count,6)

    def test_view_region_options_cannot_be_smuggled_through_exact_move(self):
        for key in ('_view_reference','_view_distance','position_tolerance_m'):
            with self.subTest(key=key),patch.object(self.p,'_execute') as execute:
                with self.assertRaisesRegex(ValueError,'Unknown target dimension'):
                    self.bot.move_to(**{key:.006})
                execute.assert_not_called()

    def test_camera_failure_does_not_repeat_completed_view_motion(self):
        self.recorded_start()
        with patch.object(self.p,'_execute',side_effect=self.plant) as execute,patch.object(self.bot,'observe',side_effect=ValueError('camera unavailable')):
            with self.assertRaisesRegex(ValueError,'camera unavailable'):self.bot.retreat_for_view(.04)
            self.assertIsNone(self.bot.motion_failure)
            with self.assertRaisesRegex(ValueError,'preceding inspect_source'):self.bot.retreat_for_view(.04)
        execute.assert_called_once()
