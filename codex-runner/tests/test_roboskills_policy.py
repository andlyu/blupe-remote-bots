"""Offline protocol tests: no session creation or physical hardware calls."""
import io
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
    def setUp(self):self.root=tempfile.TemporaryDirectory()
    def tearDown(self):self.root.cleanup()
    def policy(self,llm):
        return RoboSkillsPolicy(camera_source=Cameras(),recording_root=self.root.name,llm=llm)

    def test_upstream_agent_yields_checked_packet_and_requires_measured_completion(self):
        replies=iter(['```python\ns=bot.status()["coordinates"]\nprint(bot.move_to(left_z=s["left_z"]+.02,right_z=s["right_z"]+.02))\n```',
                      '```python\nfinish()\n```'])
        p=self.policy(lambda s,m:next(replies));obs=observation()
        points=p.build_trajectory('Raise both arms by20mm',obs,0)
        self.assertGreater(len(points),0)
        # RunnerController calls this after AWS dispatch, while a packet is
        # pending. It must not assume Responses function-call identity.
        self.assertEqual(p.public_config()['pending_packet']['waypoint_count'],len(points))
        self.assertEqual(p.public_config()['policy'],'roboskills_python_agent')
        with self.assertRaisesRegex(RuntimeError,'completion'):
            p.build_trajectory('Raise both arms by20mm',obs,0)
        end={**obs,**points[-1], 'step_id':points[-1]['step_id']+1}
        with self.assertRaisesRegex(RuntimeError,'match'):
            p.trajectory_completed(end,len(points)+1)
        p.trajectory_completed(end,len(points))
        with self.assertRaises(PolicyComplete):p.build_trajectory('Raise both arms by20mm',end,end['step_id'])
        self.assertEqual(p.public_config()['model'],'RoboSkills')
        self.assertIsNone(p._outcome['success'])

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
