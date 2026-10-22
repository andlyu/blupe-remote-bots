from unittest.mock import Mock
import unittest
import test_hosted


class HistoryEndpointTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    async def test_history_requires_browser_token_and_rejects_identity_lookup(self):
        self.assertEqual((await self.call('/api/my-runs',method='POST'))[0],401)
        browser=await self.session()
        self.assertEqual((await self.call('/api/my-runs',method='POST',cookie=browser['cookie'],csrf='wrong'))[0],403)
        for payload in ({'email':'person@example.com'}, {'episode_ids':['ep_other']}, {'offset':True}):
            self.assertEqual((await self.call('/api/my-runs',method='POST',payload=payload,**browser))[0],400)

    async def test_only_owned_runs_survive_reload_and_new_session_is_empty(self):
        browser=await self.session()
        visitor=next(iter(self.app.visitors.values()))
        visitor.runner_session_id='owned-session'
        visitor.controller.status=Mock(return_value={'session_id':'owned-session','episode_id':'ep_own'})
        self.app.submission_log.record('other','submitted',{'fields':{'email':'person@example.com'}})
        self.app.submission_log.record('other','lifecycle',{'episode_id':'ep_other'})
        self.app.past_runs=Mock()
        self.app.past_runs.page.side_effect=lambda offset,episode_ids,robot_id: {
            'runs':[{'episode_id':eid,'robot_id':robot_id} for eid in sorted(episode_ids)],
            'next_offset':None,'stale':False}
        for _ in range(2):
            code,data,_=await self.call('/api/my-runs',method='POST',**browser)
            self.assertEqual(code,200)
            self.assertEqual([row['episode_id'] for row in data['runs']],['ep_own'])
            self.assertNotIn('email',str(data))
        other=await self.session()
        code,data,_=await self.call('/api/my-runs',method='POST',**other)
        self.assertEqual(code,200)
        self.assertEqual(data['runs'],[])
        visitor.close()
        self.assertEqual(visitor.episode_ids,set())

    async def test_unowned_controller_state_does_not_enter_personal_history(self):
        browser=await self.session()
        visitor=next(iter(self.app.visitors.values()))
        for owner in (None, 'different-session'):
            visitor.runner_session_id=owner
            visitor.controller.status=Mock(return_value={'episode_id':'ep_other'})
            self.app.remember_runner(visitor)
        self.assertEqual(visitor.episode_ids,set())
