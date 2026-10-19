from unittest.mock import Mock
import unittest
import test_hosted


class HistoryEndpointTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    async def test_private_search_requires_browser_token_and_returns_public_rows(self):
        payload={'email':'person@example.com','episode_ids':['ep_browser']}
        self.assertEqual((await self.call('/api/my-runs',method='POST',payload=payload))[0],401)
        browser=await self.session()
        self.assertEqual((await self.call('/api/my-runs',method='POST',payload=payload,cookie=browser['cookie'],csrf='wrong'))[0],403)
        self.app.submission_log.record('s','submitted',{'fields':{'email':'PERSON@example.com'}})
        self.app.submission_log.record('s','lifecycle',{'episode_id':'ep_old'})
        self.app.past_runs=Mock()
        self.app.past_runs.page.return_value={'runs':[{'episode_id':'ep_old','robot_id':'yam-1'}],'next_offset':None,'stale':False}
        code,data,_=await self.call('/api/my-runs',method='POST',payload=payload,**browser)
        self.assertEqual(code,200)
        self.assertNotIn('email',str(data))
        self.app.past_runs.page.assert_called_once_with(0,episode_ids={'ep_browser','ep_old'},robot_id='yam-1')
        self.assertEqual((await self.call('/api/my-runs',method='POST',payload={'email':'invalid'},**browser))[0],400)
