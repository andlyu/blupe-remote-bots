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
