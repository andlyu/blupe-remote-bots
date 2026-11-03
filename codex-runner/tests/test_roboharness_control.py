"""Offline real-path command checks. urlopen is a wire spy, never hardware."""
from copy import deepcopy
import io
import json
import time
import unittest
from unittest.mock import patch

import numpy as np

from remote_yam.roboharness_control import RoboHarnessControl, InputRejected, aligned_rotation
from remote_yam.session import HttpSessionAPI, _trajectory_waypoints


def observation():
    # Synthetic test feedback using the existing canonical YAM FK fixture.
    q=np.rad2deg([-.0311,.794,.6167,-.3748,-.0364,-.0246]).tolist()
    return dict(source='hardware',robot_id='robot-ba8413962083809c',settled=True,homed=True,
        safety={'ok':True},observed_at=time.time(),left_gripper=.9992793312193716,
        right_gripper=.9947321472782467,left_joints_deg=q,right_joints_deg=q.copy())


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.obs=observation();self.control=RoboHarnessControl(self.obs['robot_id'])
        self.api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True,robot_id=self.obs['robot_id'])
        self.api._session_capabilities['offline']='synthetic-offline-capability'
        self.sent=[]
        def wire(req,**kwargs):
            self.assertEqual(req.full_url,'https://offline.invalid/v1/sessions/offline/trajectories')
            self.sent.append(json.loads(req.data))
            return io.BytesIO(b'{"accepted":true}')
        self.patch=patch('remote_yam.session.request.urlopen',side_effect=wire)
        self.patch.start();self.addCleanup(self.patch.stop)

    def submit(self,command,**kwargs):
        points=self.control.build(command,self.obs,kwargs.pop('first_step_id',7),**kwargs)
        self.api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10.,points)
        return self.sent[-1]

    def test_both_grippers_endpoints_partial_fractional_starts_wire_and_holds(self):
        for arm in ('left','right'):
            for target in (0.,1.,.37,1e-15,1-1e-15):
                with self.subTest(arm=arm,target=target):
                    packet=self.submit(dict(kind='gripper',arm=arm,value=target))
                    points=packet['waypoints'];other='right' if arm=='left' else 'left'
                    self.assertEqual(points[-1][arm+'_gripper'],target)
                    self.assertEqual(packet['cadence_hz'],10.)
                    self.assertEqual([p['step_id'] for p in points],list(range(7,7+len(points))))
                    previous=self.obs[arm+'_gripper']
                    for p in points:
                        self.assertGreaterEqual(p[arm+'_gripper'],0)
                        self.assertLessEqual(p[arm+'_gripper'],1)
                        self.assertLessEqual(abs(p[arm+'_gripper']-previous),.1+1e-12)
                        previous=p[arm+'_gripper']
                        for side in ('left','right'):self.assertEqual(p[side+'_joints_deg'],self.obs[side+'_joints_deg'])
                        self.assertEqual(p[other+'_gripper'],self.obs[other+'_gripper'])
                    self.assertEqual(_trajectory_waypoints(points),points)

    def test_invalid_requests_and_negative_residual_send_zero(self):
        for arm in ('left','right'):
            for value in (-1e-16,-.1,1+1e-15,2,float('nan'),float('inf'),True,None,'0'):
                with self.subTest(arm=arm,value=value):
                    before=len(self.sent)
                    with self.assertRaises(InputRejected):self.submit(dict(kind='gripper',arm=arm,value=value))
                    self.assertEqual(len(self.sent),before)
        bad=dict(self.obs,step_id=7);bad['left_gripper']=-1.1102230246251565e-16
        with self.assertRaises(ValueError):_trajectory_waypoints([{k:bad[k] for k in ('step_id','left_joints_deg','right_joints_deg','left_gripper','right_gripper')}])

    def test_adjustment_both_arms_cartesian_endpoint_pacing_and_untouched_state(self):
        for arm in ('left','right'):
            for axis in range(3):
                with self.subTest(arm=arm,axis=axis):
                    delta=[0.,0.,0.];delta[axis]=.005
                    start=self.control.pose_summary(self.obs)
                    packet=self.submit(dict(kind='adjust_pose',arm=arm,delta_m=delta,rotation_vector_rad=[0,0,0]))
                    previous=np.deg2rad(self.obs['left_joints_deg']+self.obs['right_joints_deg'])
                    other='right' if arm=='left' else 'left'
                    for p in packet['waypoints']:
                        q=np.deg2rad(p['left_joints_deg']+p['right_joints_deg'])
                        self.assertLessEqual(np.max(np.abs(q-previous)),.03+1e-12);previous=q
                        self.assertEqual(p[other+'_joints_deg'],self.obs[other+'_joints_deg'])
                        for side in ('left','right'):self.assertEqual(p[side+'_gripper'],self.obs[side+'_gripper'])
                    final={**self.obs,**packet['waypoints'][-1],'observed_at':time.time()}
                    end=self.control.pose_summary(final)
                    np.testing.assert_allclose(np.array(end[arm]['position_m'])-start[arm]['position_m'],delta,atol=2e-6)

    def test_touch_uses_current_metric_point_and_explicit_offset(self):
        start=self.control.pose_summary(self.obs)['left']['position_m']
        points={'object':{'left':start}}
        packet=self.submit(dict(kind='touch',arm='left',point_ids=['object'],offset_m=[0,0,.005]),points=points)
        final={**self.obs,**packet['waypoints'][-1],'observed_at':time.time()}
        end=self.control.pose_summary(final)['left']['position_m']
        np.testing.assert_allclose(np.array(end)-start,[0,0,.005],atol=2e-6)

    def test_alignment_rotation_resolves_axis_and_rejects_degenerate_points(self):
        rotation=aligned_rotation(np.eye(3),'x',[0,1,0])
        np.testing.assert_allclose(rotation[:,0],[0,1,0],atol=1e-12)
        np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-12)
        for value in ([0,0,0],[.0001,0,0]):
            with self.assertRaises(InputRejected):aligned_rotation(np.eye(3),'x',value)

    def test_line_and_plane_constraints_pass_real_packet_path_for_both_arms(self):
        for arm in ('left','right'):
            r=np.array(self.control.pose_summary(self.obs)[arm]['rotation_matrix'])
            # A small rotation stays within the same reachable pose neighborhood.
            from scipy.spatial.transform import Rotation
            target=Rotation.from_rotvec([0,0,.01]).as_matrix()@r
            points={'a':{arm:[0,0,0]},'b':{arm:(target[:,0]*.05).tolist()},'c':{arm:(target[:,1]*.05).tolist()}}
            for kind,ids,axis in [('align_line',['a','b'],'x'),('plane_parallel',['a','b','c'],'z')]:
                with self.subTest(arm=arm,kind=kind):
                    packet=self.submit(dict(kind=kind,arm=arm,point_ids=ids,axis=axis),points=points)
                    self.assertTrue(packet['waypoints'])
                    self.assertEqual(_trajectory_waypoints(packet['waypoints']),packet['waypoints'])

    def test_stale_feedback_readiness_bad_shapes_and_budget_reject_before_wire(self):
        for change in ({'observed_at':time.time()-3},{'settled':False},{'homed':False},
                       {'source':'simulation'},{'safety':{'ok':False}}, {'left_gripper':None},
                       {'right_joints_deg':[0]*5},{'robot_id':'other'}):
            self.obs={**observation(),**change}
            with self.subTest(change=change),self.assertRaises(InputRejected):
                self.submit(dict(kind='gripper',arm='left',value=0))
        self.obs=observation()
        for first in (-1,True,3000):
            with self.assertRaises(InputRejected):self.submit(dict(kind='gripper',arm='left',value=0),first_step_id=first)
        with self.assertRaises(InputRejected):self.submit(dict(kind='gripper',arm='left',value=0),first_step_id=2999)
        self.assertEqual(self.sent,[])

    def test_invalid_motion_modes_and_targets_zero_dispatch(self):
        commands=[{},dict(kind='gripper',arm='other',value=0),dict(kind='gripper',arm='left',value=0,extra=True),
            dict(kind='adjust_pose',arm='left',delta_m=[.100001,0,0],rotation_vector_rad=[0,0,0]),
            dict(kind='adjust_pose',arm='left',delta_m=[0,0,0],rotation_vector_rad=[0,0,.500001]),
            dict(kind='adjust_pose',arm='left',delta_m=[float('nan'),0,0],rotation_vector_rad=[0,0,0]),
            dict(kind='touch',arm='left',point_ids=['missing'],offset_m=[0,0,0]),
            dict(kind='touch',arm='left',point_ids=['a'],offset_m=[0,0,0])]
        for command in commands:
            with self.subTest(command=command),self.assertRaises(InputRejected):self.submit(command,points={'a':{'left':[.149999,0,.1]}})
        self.assertEqual(self.sent,[])


if __name__=='__main__':unittest.main()
