import unittest
import test_hosted


class VideoRequestHostedTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    async def test_request_is_forwarded_without_smtp_configuration(self):
        browser = await self.session()
        payload = dict(provider='openai',api_key='test-visitor-key',prompt='Move block',email_run_video=True)
        self.assertEqual((await self.call('/api/run',method='POST',payload=payload,**browser))[0],400)
        payload['email']='runner@example.com'
        code,result,_=await self.call('/api/run',method='POST',payload=payload,**browser)
        self.assertEqual(code,200,result)
        visitor=next(iter(self.app.visitors.values()))
        self.assertTrue(visitor.controller._session_api.api.create_requests[0]['email_run_video'])
