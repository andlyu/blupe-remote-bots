"""Actual installed jaw-slide axes, not canonical visual finger proxies."""
from pathlib import Path
from copy import deepcopy
import json,importlib.util
from unittest import TestCase,skipUnless
from unittest.mock import patch
import numpy as np
from scipy.spatial.transform import Rotation
import test_roboskills_orientation as contract

REFERENCE=json.loads((Path(__file__).parent/'fixtures/roboskills-physical-gripper-axis.json').read_text())
ENGAGEMENT=json.loads((Path(__file__).parent/'fixtures/roboskills-pad-engagement.json').read_text())

def matrix(quat):
    w,x,y,z=quat
    return Rotation.from_quat([x,y,z,w]).as_matrix()

class InstalledJawAxes(TestCase):
    def test_installed_joint_transforms_define_grasp_y_opening(self):
        site=matrix(REFERENCE['grasp_site_quat_wxyz'])
        for jaw in REFERENCE['jaws']:
            axis=site.T@matrix(jaw['body_quat_wxyz'])@jaw['axis_in_tip']
            np.testing.assert_allclose(axis,jaw['axis_in_native_grasp'],atol=1e-12)
            np.testing.assert_allclose(abs(axis),[0,1,0],atol=1e-5)

@skipUnless(importlib.util.find_spec('roboskills'),'Install pinned RoboSkills runtime')
class PhysicalOpeningContract(TestCase):
    setUp=contract.OrientationContract.setUp
    tearDown=contract.OrientationContract.tearDown
    plant=contract.OrientationContract.plant
    setUpGeometry=contract.OrientationContract.setUpGeometry

    def test_actual_empty_grasp_reports_pad_midpoint_above_measured_top(self):
        self.p._completed_moves=1
        for row in ENGAGEMENT['recorded_poses']:
            self.p._state=deepcopy(row['state'])
            with patch.object(self.p,'_execute') as execute:
                status=self.bot.status()
            execute.assert_not_called()
            geometry=status['nominal_pad_pose'];self.assertTrue(geometry['available'])
            self.assertEqual(geometry['measured_step_id'],row['step'])
            midpoint=np.array(geometry['arms']['left']['pad_midpoint_base_m'])
            expected=np.mean([x['center_base_m'] for x in row['pads_at_closed_reference']],axis=0)
            axes=np.array([x['axis_in_native_grasp'] for x in REFERENCE['jaws']])
            expected+=np.array(row['rotation_base'])@axes.mean(0)*REFERENCE['nominal_contact_reference']['opening_travel_m']*row['state']['left_gripper']/2
            np.testing.assert_allclose(midpoint,expected,atol=1e-10)
            top=ENGAGEMENT['source_top_center_base_m'][2]
            self.assertGreater(midpoint[2]-top,.006)
            self.assertLess(abs(row['object_center_beyond_max_tip_along_tool_z_m']),.0002)
            self.assertIn('not',geometry['scope'])

    def test_nominal_pad_pose_tracks_both_fractional_jaws_in_each_arm_base(self):
        self.p._completed_moves=1
        for fraction in (0.,.4333838274543747,1.):
            for arm in ('left','right'):self.p._state[arm+'_gripper']=fraction
            with patch.object(self.p,'_execute') as execute:status=self.bot.status()
            execute.assert_not_called();reference=status['tool_geometry_reference']
            for arm in ('left','right'):
                opening=np.array(status['opening_axes_base'][arm]);approach=np.array(status['approach_axes_base'][arm]);R=np.column_stack((np.cross(opening,approach),opening,approach))
                position=np.array([status['coordinates'][arm+'_'+x] for x in 'xyz'])
                row=status['nominal_pad_pose']['arms'][arm]
                for bounds,pad,jaw in zip(reference['closed_pad_bounds_tool_m'],row['pads'],REFERENCE['jaws']):
                    center=np.mean(bounds,axis=0)+np.array(jaw['axis_in_native_grasp'])*reference['opening_travel_m']*fraction/2
                    np.testing.assert_allclose(pad['center_base_m'],position+R@center,atol=1e-10)
                np.testing.assert_allclose(row['pad_midpoint_base_m'],np.mean([x['center_base_m'] for x in row['pads']],axis=0),atol=1e-12)
                measured_gap=np.dot(np.array(row['pads'][0]['center_base_m'])-row['pads'][1]['center_base_m'],opening)
                self.assertAlmostEqual(measured_gap,reference['closed_nominal_gap_m']+reference['opening_travel_m']*fraction,delta=.00005)

    def test_initial_status_stays_compact_and_unbound_geometry_is_unavailable(self):
        self.assertNotIn('nominal_pad_pose',self.bot.status())
        self.p._completed_moves=1;self.p._workspace_profile=None
        self.assertFalse(self.bot.status()['nominal_pad_pose']['available'])

    def test_actual_upstream_clipped_status_keeps_both_pad_midpoints_visible(self):
        from roboskills.core import agent
        self.p._completed_moves=1;self.p._state=deepcopy(ENGAGEMENT['recorded_poses'][0]['state'])
        self.bot.instruction=ENGAGEMENT['task'];repl=agent.Repl(self.bot,self.bot)
        with patch.object(self.p,'_execute') as execute:
            receipt,ended,_=repl.exec('print(bot.status())')
        execute.assert_not_called();self.assertFalse(ended)
        head=receipt.split('...[clipped]...')[0]
        self.assertIn("'nominal_pad_midpoints_base_m': {'left':",head)
        summary=head.split("'nominal_pad_midpoints_base_m':",1)[1].split('}',1)[0]
        self.assertIn("'right':",summary)

    def test_recorded_shallow_band_candidates_pass_real_planning_without_dispatch(self):
        self.p._state=deepcopy(ENGAGEMENT['planning_state'])
        for row in ENGAGEMENT['nominal_band_candidates']:
            arm=row['arm'];targets={arm+'_'+axis:value for axis,value in zip('xyz',row['target_base_m'])}
            with patch.object(self.p,'_execute') as execute:
                plan=self.bot.plan_move(**targets,rotation={arm:row['rotation_base']})
            execute.assert_not_called();self.assertTrue(plan['reachable'],plan)
            self.assertFalse(plan['dispatched']);self.assertGreater(plan['waypoint_count'],0)
            self.assertGreater(row['remaining_after_additional_3mm_reference_allowance_m'],.001)

    def test_nominal_span_path_both_arms_through_canonical_transport_with_synthetic_feedback(self):
        # Software-path qualification only: no physical contacts or object result.
        for row in ENGAGEMENT['nominal_span_candidates']:
            self.setUpGeometry();self.p._state=deepcopy(ENGAGEMENT['planning_state'])
            self.p._completed_moves=0;self.p._last_move=None;self.sent=[]
            arm=row['arm'];other='right' if arm=='left' else 'left';before=deepcopy(self.p._state)
            rotation={arm:row['rotation_base']};targets=row['targets']
            with patch.object(self.p,'_execute',side_effect=self.plant):
                self.bot.move_to(**{arm+'_gripper':(.04+.001)/.095})
                for name in ('approach','grasp'):self.bot.move_to(**targets[name],rotation=rotation)
                self.bot.move_to(**{arm+'_gripper':0.})
                for name in ('lift','transfer','placement'):self.bot.move_to(**targets[name],rotation=rotation)
                self.bot.move_to(**{arm+'_gripper':1.})
                self.bot.move_to(**targets['transfer'],rotation=rotation)
            self.assertGreaterEqual(len(self.sent),9)
            points=[point for packet in self.sent for point in packet['waypoints']]
            self.assertEqual([x['step_id'] for x in points],list(range(before['step_id'],before['step_id']+len(points))))
            self.assertEqual(points[-1][arm+'_gripper'],1.)
            self.assertTrue(any(x[arm+'_gripper']==0. for x in points))
            for point in points:
                np.testing.assert_array_equal(point[other+'_joints_deg'],before[other+'_joints_deg'])
                self.assertEqual(point[other+'_gripper'],before[other+'_gripper'])

    def test_reported_opening_axis_matches_native_grasp_y_at_actual_recorded_poses(self):
        for row in REFERENCE['frame_checks']:
            self.p._state={**deepcopy(row['observation']), 'source':'hardware','settled':True,'step_id':row['step'],'episode_id':'offline','lease_id':'offline'}
            status=self.bot.status()
            for arm in row['arms']:
                expected=np.array(arm['published_native_pose'])[:3,1]
                np.testing.assert_allclose(status['opening_axes_base'][arm['arm']],expected,atol=1e-10)

    def test_station_bound_nominal_geometry_retains_native_origin_and_reference_dimensions(self):
        reference=self.p.public_config()['tool_geometry_reference'];gold=REFERENCE['nominal_contact_reference']
        self.assertTrue(reference['available']);self.assertFalse(reference['physical_contact_calibration_measured'])
        self.assertEqual(reference['jaw_opening_axis'],'Y')
        for key in ('max_tip_z_m','pad_center_z_m','opening_travel_m'):
            self.assertEqual(reference[key],gold[key])
        self.assertEqual(reference['closed_nominal_gap_m'],gold['closed_gap_m'])
        self.assertGreater(reference['max_tip_z_m'],.01)
        for i,tip in enumerate(gold['tips']):
            np.testing.assert_array_equal(reference['closed_pad_bounds_tool_m'][i],tip['pad_bounds_native_grasp_m'])
        reference['max_tip_z_m']=99
        self.assertLess(self.p.public_config()['tool_geometry_reference']['max_tip_z_m'],.011)
        self.assertNotIn('closed_pad_bounds_tool_m',self.bot.status()['tool_geometry_reference'])
        self.p._completed_moves=1
        self.assertIn('closed_pad_bounds_tool_m',self.bot.status()['tool_geometry_reference'])
        self.p._workspace_profile=None
        self.assertFalse(self.bot.status()['tool_geometry_reference']['available'])

    def test_noncontact_inspection_rejects_lower_standoff_without_dispatch(self):
        for clearance in (.07999999,.10000001,0,np.nan,np.inf,True,'0.08'):
            with self.subTest(clearance=clearance),patch.object(self.p,'_execute') as execute:
                with self.assertRaises(ValueError):self.bot.inspect_source(310,83,clearance=clearance)
                execute.assert_not_called()

    def test_inspection_standoff_endpoints_and_interior_through_actual_packets(self):
        for arm in ('left','right'):
            for clearance in (.08,.09,.10):
                self.setUpGeometry();self.sent=[];before=deepcopy(self.p._state)
                source={'points_base_m':deepcopy(contract.FIXTURE['sourcePoints'])}
                with self.subTest(arm=arm,clearance=clearance),patch.object(self.bot,'measure_depth',return_value=source),patch.object(self.p,'_execute',side_effect=self.plant),patch.object(self.bot,'observe',return_value='fresh views'):
                    self.assertEqual(self.bot.inspect_source(310,83,arm=arm,clearance=clearance),'fresh views')
                self.assertLess(self.p._last_move['position_error_m'][arm],.003)
                self.assertTrue(self.sent)
                for packet in self.sent:
                    ids=[p['step_id'] for p in packet['waypoints']]
                    self.assertEqual(ids,list(range(before['step_id'],before['step_id']+len(ids))))
                    for point in packet['waypoints']:
                        for side in ('left','right'):self.assertEqual(point[side+'_gripper'],before[side+'_gripper'])

    def test_approach_candidates_level_installed_jaw_axes_through_real_packets(self):
        options=self.bot.plan_approach(contract.FIXTURE['sourcePoints'])
        self.assertEqual({c['arm'] for c in options['candidates']},{'left','right'})
        for candidate in options['candidates']:
            arm=candidate['arm'];frame=np.array(candidate['rotation'][arm])
            self.assertLess(frame[2,2],0)
            for jaw in REFERENCE['jaws']:
                #1e-5 unit-vector component allows only the installed XML's
                # rounded body quaternions, not an actuator/contact tolerance.
                self.assertLess(abs((frame@jaw['axis_in_native_grasp'])[2]),1e-5)
            self.setUpGeometry();self.sent=[];before=deepcopy(self.p._state)
            with patch.object(self.p,'_execute',side_effect=self.plant):
                result=self.bot.move_to(**candidate['targets'],rotation=candidate['rotation'])
            self.assertLess(result['last_move']['position_error_m'][arm],.003)
            self.assertLess(result['last_move']['orientation_error_deg'][arm],2.)
            other='right' if arm=='left' else 'left'
            for packet in self.sent:
                for point in packet['waypoints']:
                    self.assertEqual(point[other+'_joints_deg'],before[other+'_joints_deg'])
                    for side in ('left','right'):self.assertEqual(point[side+'_gripper'],before[side+'_gripper'])
