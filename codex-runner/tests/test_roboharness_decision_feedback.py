"""Actual Codex parser rejects before dispatch and retains failed decisions."""
import json
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from remote_yam.codex_policy import use_codex_executor
from remote_yam.robocurve_policy import CallRecorder
from test_roboharness_contract import decision
from test_roboharness_control import observation
from test_roboharness_policy import adapter


class DecisionFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.clock=1000.
        clock=patch('time.time',side_effect=lambda:self.clock);clock.start();self.addCleanup(clock.stop)
        self.obs={**observation(),'episode_id':'ep_offline','lease_id':'lease_offline','step_id':0}

    def provider(self,finals,directory=None):
        p,source=adapter();source.position={a:v['position_m'] for a,v in p._geometry.pose_summary(self.obs).items()}
        p.refresh_observation=lambda:{**self.obs,'observed_at':time.time()}
        if directory:p._recorder=CallRecorder(directory)
        requests=[];thread=str(uuid.uuid4())
        def executor(**request):
            requests.append(request);self.clock+=.1
            self.assertEqual(len(request['images']),3)
            final=finals[min(len(requests)-1,len(finals)-1)]
            return [{'type':'thread.started','thread_id':thread},
                {'type':'item.completed','item':{'type':'agent_message','text':final}},
                {'type':'turn.completed'}]
        use_codex_executor(p,executor);self.addCleanup(p.close_transport)
        return p,source,requests

    def invalid(self):
        # Used adjustment components must be numbers, including zero; null is
        # reserved for fields unused by the selected primitive.
        return json.dumps(decision(primitive=5,arm=0,x=0,y=0,z=.005,rx=None,ry=None,rz=None))

    def test_tool_field_rejection_has_fresh_feedback_before_one_valid_packet(self):
        valid=json.dumps(decision(primitive=6,arm=0,gripper=.37))
        p,source,requests=self.provider([self.invalid(),valid])
        with patch('remote_yam.session.request.urlopen') as wire:
            packet=p.build_trajectory('Synthetic offline model correction',self.obs,0)
            wire.assert_not_called()
        self.assertEqual(len(requests),2);self.assertEqual(p._failures,1)
        self.assertGreaterEqual(source.calls,3)
        self.assertIn('rx',requests[1]['prompt']);self.assertIn('dispatched',requests[1]['prompt'])
        self.assertEqual(packet[-1]['left_gripper'],.37)
        self.assertEqual(packet[-1]['right_joints_deg'],self.obs['right_joints_deg'])

    def test_three_semantic_rejections_stop_with_no_pending_packet_or_wire(self):
        p,_,requests=self.provider([self.invalid()])
        with patch('remote_yam.session.request.urlopen') as wire:
            with self.assertRaisesRegex(RuntimeError,'Three local input rejections'):
                p.build_trajectory('Synthetic offline rejection limit',self.obs,0)
            wire.assert_not_called()
        self.assertEqual(len(requests),3);self.assertIsNone(p._pending)

    def test_syntax_failure_is_retained_privately_and_never_retried_or_dispatched(self):
        raw='not JSON; synthetic-private@example.invalid'
        with tempfile.TemporaryDirectory() as directory:
            p,_,requests=self.provider([raw],directory);events=[]
            p._interaction=lambda kind,message,**details:events.append((kind,message,details))
            with patch('remote_yam.session.request.urlopen') as wire:
                with self.assertRaisesRegex(RuntimeError,'malformed JSON'):
                    p.build_trajectory('Synthetic offline syntax failure',self.obs,0)
                wire.assert_not_called()
            self.assertEqual(len(requests),1);self.assertIsNone(p._pending)
            rows=[json.loads(s) for s in (p._recorder.path/'calls.jsonl').read_text().splitlines()]
            rejected=[r for r in rows if r['kind']=='structured_decision']
            self.assertEqual(len(rejected),1);self.assertEqual(rejected[0]['final_text'],raw)
            self.assertNotIn('synthetic-private@example.invalid',json.dumps(events))


if __name__=='__main__':unittest.main()
