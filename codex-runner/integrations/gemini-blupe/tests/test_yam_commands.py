"""Offline command path through the real Session API serializer; no robot I/O."""
from copy import deepcopy
import io
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('GEMINI_TEST_RUNNER_ROOT', Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from yam_commands import YamCommands, CommandRejected, CADENCE_HZ
from remote_yam import session


class CommandContractTests(unittest.TestCase):
    def setUp(self):
        self.compiler = YamCommands(ROOT)
        self.feedback = dict(left_joints_deg=[math.degrees(q) for q in (.12345, 1.6, 1.2, -1.1, .01234, -.23456)],
                             right_joints_deg=[math.degrees(q) for q in (-.23456, 1.4, 1.3, -1.2, -.12345, .34567)],
                             left_gripper=.9992793312193716, right_gripper=.412345678)
        self.sent = []
        self.api = session.HttpSessionAPI('https://offline.invalid', supports_trajectories=True)
        self.api._session_capabilities['session'] = 'synthetic-offline-capability'
        def transport(request, **kwargs):
            self.sent.append(json.loads(request.data))
            return io.BytesIO(b'{"ok":true}')
        self.spy = patch.object(session.request, 'urlopen', transport)
        self.spy.start(); self.addCleanup(self.spy.stop)

    def command(self, key, value, duration=1):
        return json.dumps(dict(commands={key:value}, duration_s=duration))

    def compile_and_serialize(self, raw, first=7, feedback=None):
        points = self.compiler.compile(raw, feedback or self.feedback, first)
        self.api.submit_trajectory('session','episode','lease','stable-test-packet',CADENCE_HZ,points)
        return self.sent[-1]['waypoints']

    def test_gripper_endpoints_fractional_starts_and_untouched_state(self):
        for arm in ('left','right'):
            for start in (0.,1.,.9992793312193716):
                for target in (0.,1.,.375):
                    with self.subTest(arm=arm,start=start,target=target):
                        feedback=deepcopy(self.feedback); feedback[arm+'_gripper']=start
                        points=self.compile_and_serialize(self.command(arm+'/follower/goal_position/gripper',target),feedback=feedback)
                        self.assertEqual(len(points),10); self.assertEqual([p['step_id'] for p in points],list(range(7,17)))
                        self.assertEqual(points[-1][arm+'_gripper'],target)
                        other='right' if arm=='left' else 'left'
                        for point in points:
                            self.assertTrue(0<=point[arm+'_gripper']<=1)
                            self.assertEqual(point[other+'_gripper'],feedback[other+'_gripper'])
                            for side in ('left','right'):self.assertEqual(point[side+'_joints_deg'],feedback[side+'_joints_deg'])

    def test_all_twelve_joint_numeric_endpoints_and_preservation(self):
        for arm_index,arm in enumerate(('left','right')):
            for joint in range(6):
                index=arm_index*6+joint
                low=self.compiler.safety['joint_lower_rad'][index];high=self.compiler.safety['joint_upper_rad'][index]
                for target in (low,math.nextafter(low,high),(low+high)/2,math.nextafter(high,low),high):
                    with self.subTest(arm=arm,joint=joint,target=target):
                        points=self.compile_and_serialize(self.command(f'{arm}/follower/goal_position/joint{joint+1}',target,10))
                        decoded=math.radians(points[-1][arm+'_joints_deg'][joint])
                        self.assertLessEqual(abs(decoded-target),math.ulp(target))
                        for point in points:
                            value=math.radians(point[arm+'_joints_deg'][joint])
                            self.assertTrue(math.isfinite(value))
                            self.assertTrue(low<=value<=high, f'Wire endpoint {value!r} outside [{low!r},{high!r}]')
                            for side in ('left','right'):
                                self.assertEqual(point[side+'_gripper'],self.feedback[side+'_gripper'])
                                for i in range(6):
                                    if (side,i)!=(arm,joint):self.assertEqual(point[side+'_joints_deg'][i],self.feedback[side+'_joints_deg'][i])

    def test_invalid_requests_are_rejected_before_any_transport(self):
        key='left/follower/goal_position/gripper'
        bad=[self.command(key,v) for v in (-1e-16,1+1e-15,float('nan'),float('inf'),True,'0',None)]
        bad += ['not JSON','[]',self.command('unknown',0),self.command(key,0,1e308),self.command(key,0,False),'{"commands":{"'+key+'":2,"'+key+'":0},"duration_s":1}']
        for arm_index,arm in enumerate(('left','right')):
            for j in range(6):
                i=arm_index*6+j
                for target in (math.nextafter(self.compiler.safety['joint_lower_rad'][i],-math.inf),math.nextafter(self.compiler.safety['joint_upper_rad'][i],math.inf)):
                    bad.append(self.command(f'{arm}/follower/goal_position/joint{j+1}',target,10))
        for raw in bad:
            with self.subTest(raw=raw[:100]):
                before=len(self.sent)
                with self.assertRaises(CommandRejected) as error:self.compile_and_serialize(raw)
                self.assertFalse(error.exception.dispatched);self.assertEqual(len(self.sent),before)

    def test_existing_speed_and_packet_session_budgets_are_preserved(self):
        key='left/follower/goal_position/joint1';start=math.radians(self.feedback['left_joints_deg'][0])
        max_step=self.compiler.safety['max_joint_velocity_rad_s']/CADENCE_HZ
        self.compile_and_serialize(self.command(key,start+max_step*(1-1e-8),.1))
        before=len(self.sent)
        for raw,first in ((self.command(key,start+max_step*(1+1e-8),.1),7),(self.command(key,start,30.1),0),(self.command(key,start,.2),2999),(self.command(key,start),True)):
            with self.assertRaises(CommandRejected):self.compile_and_serialize(raw,first)
        self.assertEqual(len(self.sent),before)
        self.assertEqual(self.compile_and_serialize(self.command(key,start,.1),2999)[-1]['step_id'],2999)


if __name__ == '__main__':
    unittest.main()
