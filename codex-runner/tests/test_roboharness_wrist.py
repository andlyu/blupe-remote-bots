"""Selected wrist depth uses measured FK, never a mounting matrix as base pose."""
from copy import deepcopy
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock,patch
import numpy as np

from remote_yam.api_depth import DepthSnapshot
from remote_yam.cameras import CameraFrame
from remote_yam.roboharness_contract import decision_response
from remote_yam.roboharness_control import InputRejected
from remote_yam.roboharness_policy import RoboHarnessAdapter
from remote_yam.session import HttpSessionAPI,_trajectory_waypoints
from remote_yam.run_changes import snapshot as run_snapshot
from test_roboharness_contract import decision
from test_roboharness_control import observation
from test_roboharness_policy import REPORT,API


class PairedCamera:
    def __init__(self,role,report):self.grounding_camera=role;self.report=report;self.snapshots={}
    def capture_for_policy(self,observation,**kwargs):
        role=self.grounding_camera
        sample=DepthSnapshot(np.zeros((480,640,3),dtype='uint8'),np.full((480,640),.1),
            dict(camera=role,captured_at=time.time(),sensor_serial='synthetic-'+role,
                 calibration_id=self.report['calibration_id']),deepcopy(self.report),b'')
        self.snapshots={role:sample}
        return [CameraFrame(r,sample.image(),time.time()) for r in ('top','left','right')]


def policy(role,report=REPORT):
    source=PairedCamera(role,report)
    model=report.get('model_joint_calibration') or report['native_joint_calibration']
    p=RoboHarnessAdapter(API,report['robot_id'],report,
        expected_calibration_id=report['calibration_id'],
        expected_model_calibration_id=model['calibration_id'],
        camera_source=source,grounding_camera=role)
    p._geometry.clock=lambda:time.time()
    return p,source


class WristTests(unittest.TestCase):
    def setUp(self):
        clock=patch('time.time',return_value=1000.);clock.start();self.addCleanup(clock.stop)
        self.obs={**observation(),'episode_id':'ep_offline','lease_id':'lease_offline','step_id':0}

    def test_both_wrist_cameras_project_through_measured_native_grasp_to_each_base(self):
        yam1=json.loads((Path(__file__).parent/'fixtures/roboharness-yam1-calibration.json').read_text())
        for report,spacing in ((REPORT,.62),(yam1,.50)):
            for role in ('left','right'):
                with self.subTest(role=role,robot=report['robot_id']):
                    obs={**self.obs,'robot_id':report['robot_id']}
                    p,source=policy(role,report);p._capture(obs);p.tracker.register('point_0',500,500)
                    poses=p._geometry.pose_summary(obs)
                    optical=source.snapshots[role].measure(320,240,arm='left',T_base_camera=np.eye(4))['point_base_m']
                    grasp=np.eye(4);grasp[:3,:3]=poses[role]['rotation_matrix'];grasp[:3,3]=poses[role]['position_m']
                    expected=grasp@np.array(report['cameras'][role]['T_grasp_camera'])@np.r_[optical,1]
                    actual=p._measure_points(obs)['point_0']
                    np.testing.assert_allclose(actual[role],expected[:3],atol=1e-12)
                    np.testing.assert_allclose(np.array(actual['right'])-actual['left'],[0,spacing,0],atol=1e-12)
                    self.assertEqual(p.tracker.summary()['camera'],role)

    def test_wrist_pose_is_refreshed_and_unknown_or_unsettled_feedback_fails_closed(self):
        p,_=policy('left');p._capture(self.obs);p.tracker.register('point_0',500,500)
        before=p._measure_points(self.obs)['point_0']['left']
        moved=deepcopy(self.obs);moved['left_joints_deg'][0]+=.2
        after=p._measure_points(moved)['point_0']['left']
        self.assertGreater(np.linalg.norm(np.array(before)-after),.0001)
        with patch('remote_yam.session.request.urlopen') as wire:
            for change in ({'source':'simulation'},{'settled':False},{'observed_at':997.}):
                with self.subTest(change=change),self.assertRaises(InputRejected):p._measure_points({**self.obs,**change})
            with self.assertRaises(InputRejected):p.tracker.measure()
            p.tracker.snapshot.calibration['cameras']['left']['parent_frame']='camera_optical'
            with self.assertRaises(InputRejected):p._measure_points(self.obs)
            wire.assert_not_called()

    def test_wrist_selected_point_runs_real_decision_parser_generator_serializer_and_validator(self):
        for index,role in enumerate(('left','right')):
            with self.subTest(role=role):
                p,source=policy(role);p._capture(self.obs);p.tracker.register('point_0',500,500)
                start=p._geometry.pose_summary(self.obs)[role]['position_m']
                surface=p._measure_points(self.obs)['point_0'][role]
                offset=np.array(start)+[0,0,.005]-surface
                p._post_json=Mock(return_value=decision_response(decision(primitive=2,arm=index,
                    point_a=0,u=500,v=500,x=float(offset[0]),y=float(offset[1]),z=float(offset[2]))))
                packet=p.build_trajectory('Synthetic offline wrist approach',self.obs,0)
                api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True,robot_id=p.robot_id)
                api._session_capabilities['offline']='synthetic-capability';sent=[]
                def wire(request,**kwargs):sent.append(json.loads(request.data));return io.BytesIO(b'{"accepted":true}')
                with patch('remote_yam.session.request.urlopen',side_effect=wire):
                    api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10.,packet)
                self.assertEqual(len(sent),1);self.assertEqual(_trajectory_waypoints(sent[0]['waypoints']),packet)
                other='right' if role=='left' else 'left'
                self.assertEqual(packet[-1][other+'_joints_deg'],self.obs[other+'_joints_deg'])
                end=p._geometry.pose_summary({**self.obs,**packet[-1]})[role]['position_m']
                np.testing.assert_allclose(np.array(end)-start,[0,0,.005],atol=2e-6)

    def test_camera_choice_and_prompt_are_immutable_after_run_initialization(self):
        p,_=policy('left');p._episode=('ep_offline','lease_offline')
        message=p._observation_message('Synthetic offline selected camera',self.obs,0)
        self.assertIn('Only LEFT WRIST is paired',p._system_prompt)
        self.assertEqual(sum(c.get('type')=='input_image' for c in message['content']),3)
        labels=[c['text'] for c in message['content'] if c.get('type')=='input_text']
        self.assertEqual(sum('SELECT METRIC POINTS HERE' in label for label in labels),1)
        self.assertIn('left camera; SELECT',str(labels))
        for camera in ('external',None,True):
            with self.assertRaises(ValueError):p.select_grounding_camera(camera)
        p._calls=1
        with self.assertRaisesRegex(ValueError,'new run'):p.select_grounding_camera('right')

    def test_actual_selected_camera_is_retained_in_run_provenance(self):
        p,_=policy('right');cfg=p.public_config();stored=run_snapshot(p,'Synthetic offline task',60)
        self.assertEqual(cfg['depth_grounding_roles'],['right'])
        self.assertEqual(stored['grounding_camera'],'right')
        self.assertEqual(stored['depth_grounding_roles'],['right'])


if __name__=='__main__':unittest.main()
