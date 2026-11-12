"""Robo-house station binding, real controller guard and parked admission."""
from copy import deepcopy
import time
import unittest
import numpy as np

import test_kinex as generic
from remote_yam.kinex_policy import KinexPackets,bounded_degrees
from remote_yam.kinex_safety import RoboHouseGuard,ROBOHOUSE,admission


def report():
    p=RoboHouseGuard().profile
    return dict(robot_id=ROBOHOUSE,base_geometry={'spacing_m':.62},
        model_joint_calibration=dict(calibration_id=p['model_calibration_id'],
            coordinate_convention=p['coordinate_convention'],canonical_model_sha256=p['canonical_model_sha256'],
            offsets_rad=deepcopy(p['offsets_rad'])))


class RoboHouseCommandContract(generic.CommandContract):
    def setUp(self):
        super().setUp();self.p=KinexPackets(ROBOHOUSE);self.obs['jetson_id']=ROBOHOUSE


class StationSafety(unittest.TestCase):
    def test_endpoint_codec_roundtrips_inside_strict_bounds_without_accepting_bad_targets(self):
        import math
        p=KinexPackets(ROBOHOUSE)
        for lo,hi in zip(p.geometry.low,p.geometry.high):
            for value in (lo,hi,math.nextafter(float(lo),math.inf),math.nextafter(float(hi),-math.inf)):
                d=bounded_degrees([value],[lo],[hi])[0]
                self.assertTrue(lo<=math.radians(d)<=hi)
                self.assertTrue(lo<=float(np.deg2rad(d))<=hi)
                self.assertLessEqual(abs(math.radians(d)-value),2e-15)
            for value in (math.nextafter(float(lo),-math.inf),math.nextafter(float(hi),math.inf)):
                with self.assertRaises(ValueError):bounded_degrees([value],[lo],[hi])

    def test_binding_rejects_station_coordinate_offsets_and_spacing_changes(self):
        g=RoboHouseGuard();g.validate_report(report())
        variants=[dict(robot_id='yam-1'),dict(native_joint_calibration={}),dict(base_geometry={'spacing_m':.5})]
        for changed in variants:
            with self.assertRaises(ValueError):g.validate_report(dict(report(),**changed))
        for key in ('calibration_id','coordinate_convention','canonical_model_sha256','offsets_rad'):
            r=report();r['model_joint_calibration'][key]=None
            with self.assertRaises(ValueError):g.validate_report(r)

    def test_collision_model_compiles_body_masks_and_rejects_real_contact_before_wire(self):
        p=KinexPackets(ROBOHOUSE)
        q=[-.446244487305557,3.2990436614422296,2.536400814003126,1.236487925336928,-.27059812067567834,-1.9782271283964064,.11984940199023507,2.1923330044767155,1.5507901896968208,1.0680288401844114,.22228501741538714,.9400403867926818]
        positions=p.guard.positions(q)
        self.assertTrue(all(p.guard.guard._tip_inside_workspace(a,v) for a,v in positions.items()))
        self.assertGreater(p.guard.data.ncon,0)
        self.assertTrue((p.guard.model.body_contype[3:8]>0).all())
        obs=generic.observation();obs.update(jetson_id=ROBOHOUSE,left_joints_deg=np.rad2deg(q[:6]).tolist(),right_joints_deg=np.rad2deg(q[6:]).tolist())
        with self.assertRaisesRegex(ValueError,'predicted_collision'):p.build('left_gripper',dict(actions=[.37],duration_s=1),obs,0)

    def test_workspace_rejects_measured_state_before_wire(self):
        p=KinexPackets(ROBOHOUSE)
        q=[-.11009357147282511,.8264009699047197,1.9539344957032327,.11474266031406484,.4970944266271941,-.2203365832998644,-2.3061631195062167,.5492147376107445,1.0005293957196493,.6095384328892596,-.9757914523094133,-1.6920298851705506]
        obs=generic.observation();obs.update(jetson_id=ROBOHOUSE,left_joints_deg=np.rad2deg(q[:6]).tolist(),right_joints_deg=np.rad2deg(q[6:]).tolist())
        with self.assertRaisesRegex(ValueError,'outside_workspace'):p.build('left_gripper',dict(actions=[.37],duration_s=1),obs,0)

    def test_current_parked_queue_attestation_only_allows_admission(self):
        obs=generic.observation();obs.update(jetson_id=ROBOHOUSE,mode='DISABLED',queue_ready=True,homed=False,settled=False,safety={'ok':False,'estop_engaged':False,'reason':'hardware_not_initialized'})
        queue=dict(generated_at=time.time(),stations=[dict(jetson_id=ROBOHOUSE,connected=True,queue_ready=True,available=False)])
        self.assertTrue(admission(queue,obs,ROBOHOUSE)[0])
        # Admission is not actuator permission: the exact same observation fails motion.
        with self.assertRaises(ValueError):KinexPackets(ROBOHOUSE).build('left_gripper',dict(actions=[0],duration_s=1),obs,0)
        for changed in ({'observed_at':time.time()-3},{'source':'simulation'},{'jetson_id':'other'},{'queue_ready':False},{'safety':{'ok':False,'estop_engaged':True,'reason':'hardware_not_initialized'}}):
            self.assertFalse(admission(queue,dict(obs,**changed),ROBOHOUSE)[0])
        for changed in ({'connected':False},{'queue_ready':False}):
            other=deepcopy(queue);other['stations'][0].update(changed)
            self.assertFalse(admission(other,obs,ROBOHOUSE)[0])
        self.assertFalse(admission(dict(queue,generated_at=time.time()-6),obs,ROBOHOUSE)[0])
