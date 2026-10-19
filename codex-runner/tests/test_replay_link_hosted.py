from unittest.mock import Mock
import json
import unittest
import test_hosted


class ReplayLinkTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    async def call_replay(self, query):
        sent = []
        async def receive():
            return {'type':'http.request', 'body':b''}
        async def send(value):
            sent.append(value)
        await self.app({'type':'http','method':'GET','path':'/api/past-runs',
                        'query_string':query,'headers':[(b'host',b'robot.example')]},receive,send)
        return sent[0]['status'], json.loads(b''.join(v.get('body',b'') for v in sent[1:]))

    async def test_exact_replay_is_public_and_has_existing_result_context(self):
        self.app.past_runs = Mock()
        self.app.past_runs.get.return_value = {'episode_id':'ep_old','robot_id':'yam-1'}
        self.app.run_names = Mock()
        self.app.run_names.names.return_value = {'ep_old':'Runner'}
        self.app.run_names.results.return_value = {'ep_old':{'result':'Stopped'}}
        code,body=await self.call_replay(b'episode_id=ep_old')
        self.assertEqual(code,200)
        self.assertEqual(body['runs'][0]['runner_name'],'Runner')
        self.assertEqual(body['runs'][0]['result'],'Stopped')
        self.app.past_runs.get.assert_called_once_with('ep_old')
        self.app.past_runs.page.assert_not_called()

    async def test_missing_and_invalid_episode_are_distinct(self):
        self.app.past_runs = Mock()
        self.app.past_runs.get.return_value = None
        code,body=await self.call_replay(b'episode_id=ep_missing')
        self.assertEqual(code,200)
        self.assertEqual(body['runs'],[])
        code,_=await self.call_replay(b'episode_id=..%2Fprivate')
        self.assertEqual(code,400)

    async def test_run_receipt_is_available_before_video_and_has_its_name_outcome_and_metrics(self):
        self.app.past_runs = Mock()
        self.app.past_runs.get.return_value = None
        self.app.run_names.remember_metadata('ep_processing','yam-1','Move duck',123)
        self.app.run_names.remember('ep_processing','Andrew')
        self.app.run_names.remember_result('ep_processing',{'provider':{'outcome':{'status':'done','summary':'Duck placed'}},
            'run_metrics':{'model_s':12,'execution_s':4},'step_timings':[{'step':1,'model_s':12}]})
        code,body=await self.call_replay(b'episode_id=ep_processing')
        self.assertEqual(code,200)
        run=body['runs'][0]
        self.assertEqual(run['runner_name'],'Andrew')
        self.assertEqual(run['prompt'],'Move duck')
        self.assertEqual(run['result'],'Success')
        self.assertEqual(run['run_metrics']['model_s'],12)
        self.assertEqual(run['step_timings'][0]['step'],1)
        self.assertIsNone(run['video_url'])
        self.assertEqual(run['video_status'],'processing')
        self.app.run_names.remember_metadata('ep_other','other','Other robot',1)
        code,body=await self.call_replay(b'episode_id=ep_other')
        self.assertEqual(body['runs'],[])
