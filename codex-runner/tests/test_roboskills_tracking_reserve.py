"""Sample correction room through real native packets; never physical transport."""
from pathlib import Path
from copy import deepcopy
from unittest import TestCase,skipUnless
from unittest.mock import patch
import importlib.util,json
import numpy as np
from remote_yam import roboskills_policy as policy
import test_roboskills_orientation as fixtures

RECORDED=json.loads((Path(__file__).parent/'fixtures/roboskills-correction-room.json').read_text())

@skipUnless(importlib.util.find_spec('roboskills'),'Install the pinned RoboSkills runtime')
class TrackingReserve(TestCase):
    setUp=fixtures.OrientationContract.setUp
    tearDown=fixtures.OrientationContract.tearDown

    def prepare(self):
        self.p._state=deepcopy(RECORDED['before']);self.p._geometry.observe(self.p._state)
        self.p._completed_moves=8

    def candidate(self,tilt):
        return next(x for x in RECORDED['candidates'] if x['tilt_deg']==tilt)

    def test_actual_nominally_reachable_view_has_insufficient_sampled_correction_room(self):
        self.prepare();before=deepcopy(self.p._state)
        rotations=tuple(x.copy() for x in self.p._geometry.start_rotations);modes=self.p._geometry.attitude_references.copy()
        self.p._local_rejection={'reason':'retained previous local rejection','dispatched':False};rejection=deepcopy(self.p._local_rejection)
        with patch.object(self.p,'_execute') as execute:
            result=self.bot.plan_move(**RECORDED['target'],rotation={'left':RECORDED['rotation']})
        execute.assert_not_called();self.assertTrue(result['reachable'])
        reserve=result['tracking_reserve'];self.assertTrue(reserve['applicable']);self.assertFalse(reserve['passed'])
        self.assertEqual(reserve['max_axis_offset_m'],.008);self.assertEqual(reserve['total_samples'],26)
        self.assertGreater(reserve['checked_samples'],0);self.assertLessEqual(reserve['checked_samples'],26)
        self.assertIn('unreachable',reserve['reason']);self.assertIn('not',reserve['scope'])
        self.assertEqual(self.p._state,before);self.assertEqual(self.p._local_rejection,rejection)
        self.assertEqual(self.p._geometry.attitude_references,modes)
        for a,b in zip(rotations,self.p._geometry.start_rotations):np.testing.assert_array_equal(a,b)

    def test_alternative_view_passes_all_26_canonical_samples(self):
        self.prepare();row=self.candidate(15)
        with patch.object(self.p,'_execute') as execute:
            result=self.bot.plan_move(**row['target'],rotation={'left':row['rotation']})
        execute.assert_not_called();self.assertTrue(result['reachable'])
        reserve=result['tracking_reserve'];self.assertTrue(reserve['passed'])
        self.assertEqual(reserve['checked_samples'],26);self.assertEqual(reserve['total_samples'],26)
        self.assertNotIn('failed_offset_m',reserve)

    def test_actual_rejected_correction_stays_rejected_without_dispatch(self):
        self.prepare();self.p._state=deepcopy(RECORDED['after_feedback'])
        with patch.object(self.p,'_execute') as execute:
            result=self.bot.plan_move(**RECORDED['actual_corrected_target'],rotation={'left':RECORDED['rotation']})
        execute.assert_not_called();self.assertFalse(result['reachable']);self.assertIn('unreachable',result['reason'])

    def test_initial_planning_does_not_scan_or_change_startup_path(self):
        self.prepare();self.p._completed_moves=0;row=self.candidate(15)
        with patch.object(policy,'_trajectory_waypoints',wraps=policy._trajectory_waypoints) as serializer,patch.object(self.p,'_execute') as execute:
            result=self.bot.plan_move(**row['target'],rotation={'left':row['rotation']})
        self.assertTrue(result['reachable']);self.assertNotIn('tracking_reserve',result)
        self.assertEqual(serializer.call_count,1);execute.assert_not_called()

    def test_gripper_only_plan_is_not_a_cartesian_reserve_scan(self):
        self.prepare()
        with patch.object(policy,'_trajectory_waypoints',wraps=policy._trajectory_waypoints) as serializer,patch.object(self.p,'_execute') as execute:
            result=self.bot.plan_move(left_gripper=.45)
        execute.assert_not_called();self.assertTrue(result['reachable'])
        self.assertFalse(result['tracking_reserve']['applicable']);self.assertIsNone(result['tracking_reserve']['passed'])
        self.assertEqual(result['tracking_reserve']['checked_samples'],0);self.assertEqual(serializer.call_count,1)

    def test_right_and_dual_arm_samples_use_each_native_base(self):
        self.prepare()
        for targets,total in ((dict(right_x=.28,right_y=0.,right_z=.18),26),
                              (dict(left_x=.42,left_y=-.20,left_z=.10,right_x=.28,right_y=0.,right_z=.18),52)):
            with self.subTest(targets=targets),patch.object(self.p,'_execute') as execute:
                result=self.bot.plan_move(**targets)
            execute.assert_not_called();self.assertTrue(result['reachable'],result)
            self.assertTrue(result['tracking_reserve']['passed'],result)
            self.assertEqual(result['tracking_reserve']['checked_samples'],total)

    def test_invalid_input_and_stop_do_not_expand_actuation(self):
        self.prepare()
        with patch.object(self.p,'_execute') as execute:
            # Existing strict recording rejects nonfinite input with ValueError;
            # finite out-of-range requests return the structured local rejection.
            with self.assertRaises(ValueError):self.bot.plan_move(left_x=float('nan'))
            result=self.bot.plan_move(left_gripper=1.0000000001);self.assertFalse(result['reachable'])
            self.assertNotIn('tracking_reserve',result)
            self.p._failure='Native Stop retained'
            with self.assertRaisesRegex(RuntimeError,'Stop'):self.bot.plan_move(left_x=.4)
        execute.assert_not_called()
