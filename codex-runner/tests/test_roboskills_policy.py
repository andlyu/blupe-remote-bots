"""Offline protocol tests: no session creation or physical hardware calls."""
import io
from unittest.mock import patch
import importlib.util
import tempfile
import threading
import time
import unittest

import numpy as np
from PIL import Image
from remote_yam.cameras import CameraFrame
from remote_yam.providers import PolicyComplete
from remote_yam.roboskills_policy import RoboSkillsPolicy


def observation():
    return dict(source='hardware',episode_id='ep_unit',lease_id='lease_unit',step_id=0,
        settled=True,homed=True,left_gripper=1.,right_gripper=1.,
        left_joints_deg=np.rad2deg([-.0311,.794,.6167,-.3748,-.0364,-.0246]).tolist(),
        right_joints_deg=np.rad2deg([-.0227,.7929,.6193,-.3794,-.033,-.028]).tolist())

class Cameras:
    def capture(self,obs):
        buf=io.BytesIO();Image.new('RGB',(32,32)).save(buf,format='JPEG')
        return [CameraFrame(n,buf.getvalue(),time.time()) for n in ('top','left','right')]

@unittest.skipUnless(importlib.util.find_spec('roboskills'),'Install the optional pinned RoboSkills runtime')
class Tests(unittest.TestCase):
    def setUp(self):self.root=tempfile.TemporaryDirectory();self.policies=[]
    def tearDown(self):
        # Stop/join the upstream writer before deleting its temporary log root.
        for p in self.policies:
            p.request_stop()
            if p._thread:
                p._thread.join(3)
                self.assertFalse(p._thread.is_alive())
        self.root.cleanup()
    def policy(self,llm):
        p=RoboSkillsPolicy(camera_source=Cameras(),recording_root=self.root.name,llm=llm)
        self.policies.append(p)
        return p

    def test_upstream_agent_yields_checked_packet_and_requires_measured_completion(self):
        replies=iter(['```python\ns=bot.status()["coordinates"]\nprint(bot.move_to(left_z=s["left_z"]+.02,right_z=s["right_z"]+.02))\n```',
                      '```python\nfinish()\n```'])
        p=self.policy(lambda s,m:next(replies));obs={**observation(),'observed_at':100.}
        points=p.build_trajectory('Raise both arms by20mm',obs,0)
        self.assertGreater(len(points),0)
        # RunnerController calls this after AWS dispatch, while a packet is
        # pending. It must not assume Responses function-call identity.
        self.assertEqual(p.public_config()['pending_packet']['waypoint_count'],len(points))
        self.assertEqual(p.public_config()['policy'],'roboskills_python_agent')
        self.assertEqual(p.public_config()['startup_home_feedback']['observed_at'],100.)
        with self.assertRaisesRegex(RuntimeError,'completion'):
            p.build_trajectory('Raise both arms by20mm',obs,0)
        end={**obs,**points[-1], 'step_id':points[-1]['step_id']+1,'observed_at':110.}
        with self.assertRaisesRegex(RuntimeError,'match'):
            p.trajectory_completed(end,len(points)+1)
        p.trajectory_completed(end,len(points))
        with self.assertRaises(PolicyComplete):p.build_trajectory('Raise both arms by20mm',end,end['step_id'])
        self.assertEqual(p.public_config()['model'],'RoboSkills')
        self.assertEqual(p.public_config()['startup_home_feedback']['observed_at'],100.)
        self.assertIsNone(p._outcome['success'])

    def test_short_measured_move_latches_failure_and_finish_cannot_report_done(self):
        from remote_yam.roboskills_policy import RobotTools
        p=self.policy(lambda s,m:'');obs=observation()
        p._state=obs;p._identity=('ep_unit','lease_unit')
        bot=RobotTools(p,'Lift20mm')
        start=bot.status()['coordinates']
        # Use the verified IK target with a measured endpoint that stays at
        # the start. Protocol completion alone must not mark it reached.
        with patch.object(p,'_execute',return_value=obs):
            with self.assertRaisesRegex(RuntimeError,'target'):
                bot.move_to(left_z=start['left_z']+.02,right_z=start['right_z']+.02)
        self.assertEqual(bot.finish()['status'],'failed')
        with self.assertRaises(RuntimeError):bot.move_to(left_z=start['left_z'])

    def test_measured_tracking_correction_converges_without_changing_limits(self):
        from remote_yam.roboskills_policy import RobotTools
        p=self.policy(lambda s,m:'');obs=observation()
        p._state=obs;p._identity=('ep_unit','lease_unit')
        bot=RobotTools(p,'Lift20mm');start=bot.status()['coordinates'];packets=[]
        def plant(points):
            packets.append(points)
            end={**obs,**points[-1],'step_id':points[-1]['step_id']+1}
            # Static residual observed on the real joint3 drives; this is an
            # offline plant model, not a claim of physical qualification.
            end['left_joints_deg']=list(end['left_joints_deg'])
            end['right_joints_deg']=list(end['right_joints_deg'])
            end['left_joints_deg'][2]-=.75
            end['right_joints_deg'][2]-=.57
            return end
        with patch.object(p,'_execute',side_effect=plant):
            end=bot.move_to(left_z=start['left_z']+.02,right_z=start['right_z']+.02)
        self.assertGreater(len(packets),1)
        self.assertLessEqual(len(packets),3)
        self.assertLess(abs(end['coordinates']['left_z']-start['left_z']-.02),.003)
        self.assertLess(max(p._last_move['position_error_m'].values()),.003)
        for before,after in zip(packets,packets[1:]):
            self.assertEqual(after[0]['step_id'],before[-1]['step_id']+1)

    def test_tracking_offset_accumulates_persistent_measured_residual(self):
        from remote_yam.roboskills_policy import RobotTools
        p=self.policy(lambda s,m:'');obs=observation();p._state=obs;p._identity=('ep_unit','lease_unit')
        bot=RobotTools(p,'Lift20mm');start=bot.status()['coordinates'];goal=start['left_z']+.02
        # Replay known, completed endpoint shortfalls:4mm then3.5mm. Dropping
        # the previous offset leaves a permanent error on a compliant drive.
        endpoints=[]
        for shortfall in (.004,.0035,0):
            pts=p._geometry.build({'left_z':goal-shortfall},obs,0)
            endpoints.append({**obs,**pts[-1]})
        results=iter(endpoints)
        def complete(points):
            return {**next(results),'step_id':points[-1]['step_id']+1}
        with patch.object(p._geometry,'build',wraps=p._geometry.build) as build,patch.object(p,'_execute',side_effect=complete):
            bot.move_to(left_z=goal)
        self.assertAlmostEqual(build.call_args_list[2].args[0]['left_z']-goal,.0075,places=4)

    def test_uncertain_packet_is_never_retried_or_cleared_by_finish(self):
        from remote_yam.roboskills_policy import RobotTools
        p=self.policy(lambda s,m:'');p._state=observation();p._identity=('ep_unit','lease_unit')
        bot=RobotTools(p,'Test');s=bot.status()['coordinates']
        with patch.object(p,'_execute',side_effect=TimeoutError('uncertain')) as dispatch:
            with self.assertRaises(TimeoutError):bot.move_to(left_z=s['left_z']+.02)
        dispatch.assert_called_once()
        self.assertEqual(bot.finish()['status'],'failed')

    def test_status_uses_installed_measured_feedback_without_duplicate_fetch(self):
        from remote_yam.roboskills_policy import RobotTools
        p=self.policy(lambda s,m:'');p._state=observation()
        p._identity=('ep_unit','lease_unit')
        p.refresh_observation=lambda: (_ for _ in ()).throw(AssertionError('duplicate network read'))
        self.assertIn('left_z',RobotTools(p,'Test').status()['coordinates'])

    def test_simulated_feedback_and_changed_lease_are_rejected(self):
        p=self.policy(lambda s,m:'```python\nfinish()\n```')
        with self.assertRaisesRegex(RuntimeError,'hardware'):
            p.build_trajectory('Test',{**observation(),'source':'simulation'},0)
        with self.assertRaisesRegex(RuntimeError,'hardware'):
            p.build_trajectory('Test',{**observation(),'lease_id':'different'},0)

    def test_stop_during_model_call_prevents_late_packet(self):
        entered,release=threading.Event(),threading.Event()
        def model(s,m):
            entered.set();release.wait(3)
            return '```python\nprint(bot.move_to(left_gripper=0))\n```'
        p=self.policy(model);errors=[]
        def run():
            try:p.build_trajectory('Test Stop',observation(),0)
            except Exception as e:errors.append(e)
        t=threading.Thread(target=run);t.start();self.assertTrue(entered.wait(3))
        p.request_stop();release.set();t.join(3)
        self.assertFalse(t.is_alive());self.assertTrue(errors);self.assertTrue(p._packets.empty())

if __name__=='__main__':unittest.main()
