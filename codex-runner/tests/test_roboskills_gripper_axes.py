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
