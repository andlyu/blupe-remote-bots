"""Bounded same-view inspection through the real decision and packet paths."""
import io
import json
import time
import unittest
import uuid
from unittest.mock import patch

import numpy as np

from remote_yam.codex_policy import use_codex_executor
from remote_yam.roboharness_contract import decision_response
from remote_yam.roboharness_control import InputRejected
from remote_yam.roboharness_tracking import KeypointTracker
from remote_yam.session import HttpSessionAPI
from test_roboharness_contract import decision
from test_roboharness_control import observation
from test_roboharness_policy import adapter


def batch(**changes):
    targets=dict(primitive=1,point_a=0,u=0,v=1000,
                 point_b=1,x=500,y=250,point_c=2,rx=1000,ry=0)
    targets.update(changes)
    return decision(**targets)


class BatchInspectionTests(unittest.TestCase):
    def setUp(self):
        clock=patch('time.time',return_value=1000.)
        clock.start();self.addCleanup(clock.stop)
        self.obs={**observation(),'episode_id':'ep_offline','lease_id':'lease_offline','step_id':0}

    def test_three_point_parser_rejects_incomplete_duplicate_and_out_of_range_tail(self):
        call=decision_response(batch())['output'][0]
        args=json.loads(call['arguments'])
        self.assertEqual(call['name'],'track_object')
        self.assertEqual(args['registrations'],[
            dict(point_id='point_0',u=0.,v=1000.),
            dict(point_id='point_1',u=500.,v=250.),
            dict(point_id='point_2',u=1000.,v=0.)])
        two=json.loads(decision_response(batch(point_c=None,rx=None,ry=None))['output'][0]['arguments'])
        self.assertEqual(two['registrations'],args['registrations'][:2])
        invalid=[batch(point_b=None),batch(point_c=1),batch(ry=None),
                 batch(rx=1000.000001),batch(x=True),batch(ry=float('nan')),
                 batch(point_c=16),batch(z=0),batch(arm=0)]
        with patch('remote_yam.session.request.urlopen') as wire:
            for value in invalid:
                with self.subTest(value=value),self.assertRaises(InputRejected):
                    decision_response(value)
            wire.assert_not_called()

    def test_batch_registration_is_atomic_and_uses_one_existing_image(self):
        p,source=adapter();source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
        p._capture(self.obs)
        tracker=p.tracker;tracker.register('point_9',300,400)
        before={k:v.copy() for k,v in tracker.points.items()};stamp=tracker.snapshot.metadata['captured_at']
        for invalid in ([dict(point_id='point_0',u=0,v=0),dict(point_id='point_1',u=1001,v=0)],
                        [dict(point_id='point_0',u=0,v=0),dict(point_id='point_0',u=1,v=1)],
                        [],[dict(point_id='point_0',u=1,v=1)]*4):
            with self.subTest(invalid=invalid),self.assertRaises(InputRejected):tracker.register_many(invalid)
            self.assertEqual(set(tracker.points),set(before))
            np.testing.assert_array_equal(tracker.points['point_9'],before['point_9'])
        registrations=json.loads(decision_response(batch())['output'][0]['arguments'])['registrations']
        tracker.register_many(registrations)
        np.testing.assert_allclose(tracker.points['point_0'],[0,79])
        np.testing.assert_allclose(tracker.points['point_1'],[49.5,19.75])
        np.testing.assert_allclose(tracker.points['point_2'],[99,0])
        self.assertEqual(tracker.snapshot.metadata['captured_at'],stamp)
        self.assertEqual(source.calls,1)
        with self.assertRaises(InputRejected):KeypointTracker().register_many(registrations)

    def provider(self,finals):
        p,source=adapter();source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
        p.refresh_observation=lambda:{**self.obs,'observed_at':time.time()}
        requests=[];thread=str(uuid.uuid4())
        def executor(**request):
            requests.append(request);self.assertEqual(len(request['images']),3)
            return [{'type':'thread.started','thread_id':thread},
                    {'type':'item.completed','item':{'type':'agent_message','text':json.dumps(finals[len(requests)-1])}},
                    {'type':'turn.completed'}]
        use_codex_executor(p,executor);self.addCleanup(p.close_transport)
        return p,source,requests

    def test_actual_codex_batch_inspects_without_dispatch_before_both_arm_fractional_packets(self):
        for arm,name in enumerate(('left','right')):
            with self.subTest(arm=name):
                p,source,requests=self.provider([batch(),decision(primitive=6,arm=arm,gripper=.37)])
                with patch('remote_yam.session.request.urlopen') as wire:
                    packet=p.build_trajectory('Synthetic same-view inspection then gripper',self.obs,0)
                    wire.assert_not_called()
                self.assertEqual(len(requests),2)
                self.assertEqual(set(p.tracker.points),{'point_0','point_1','point_2'})
                self.assertIn('point_2',requests[1]['prompt'])
                self.assertEqual(p._failures,0)
                api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True)
                api._session_capabilities['offline']='synthetic';sent=[]
                def wire(req,**_):sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
                with patch('remote_yam.session.request.urlopen',side_effect=wire):
                    api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10,packet)
                self.assertEqual(len(sent),1)
                self.assertEqual(sent[0]['waypoints'][-1][name+'_gripper'],.37)
                held=('right','left')[arm]
                self.assertEqual(packet[-1][held+'_joints_deg'],self.obs[held+'_joints_deg'])

    def test_invalid_batch_tail_reaches_fresh_feedback_with_zero_partial_registration_or_dispatch(self):
        terminal={**decision(),'action':'give_up','reason':'Synthetic review complete'}
        p,source,requests=self.provider([batch(ry=None),terminal])
        from remote_yam.robocurve_policy import PolicyComplete
        with patch('remote_yam.session.request.urlopen') as wire:
            with self.assertRaises(PolicyComplete):
                p.build_trajectory('Synthetic invalid inspection',self.obs,0)
            wire.assert_not_called()
        self.assertEqual(p._failures,1);self.assertEqual(len(requests),2)
        self.assertFalse(p.tracker.points);self.assertIsNone(p._pending)
        self.assertIn('dispatched',requests[1]['prompt'])
        self.assertGreaterEqual(source.calls,2)


if __name__=='__main__':unittest.main()
