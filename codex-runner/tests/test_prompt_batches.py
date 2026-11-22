"""Real hosted admission/lifecycle, with hardware and external mail absent."""
import asyncio
import json
import unittest
import threading

import test_hosted


class PromptBatchTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    def payload(self):
        return dict(provider='openai', model='gpt-6.1-sol', api_key='batch-secret-key',
                    prompt='first', prompts=['first', 'second', 'third'],
                    runner_name='Fixture Runner', email='fixture@example.com', email_run_video=True)

    async def wait_for(self, predicate):
        for _ in range(300):
            if predicate():
                return
            await asyncio.sleep(.01)
        self.fail('Batch did not reach the expected lifecycle state')

    async def test_three_prompts_advance_without_browser_polling_and_keep_identity_and_opt_in(self):
        browser = await self.session()
        code, result, _ = await self.call('/api/run', method='POST', payload=self.payload(), **browser)
        self.assertEqual(code, 200, result)
        owner = next(iter(self.app.visitors.values()))
        batch = owner.prompt_batch
        batch.poll_s = .01
        self.assertEqual(result['prompt_batch']['total'], 3)
        self.assertFalse(self.app.visitor_expired(owner, owner.born + 100000))
        born = owner.born
        owner.born -= self.app.lifetime_seconds + 1
        self.assertEqual((await self.call('/api/status', **browser))[0], 200)
        owner.born = born
        for index in range(3):
            await self.wait_for(lambda: batch.index == index and owner.controller.busy())
            state = owner.controller.status()
            owner.last_launch -= 5  # Do not spend real seconds on the existing interval.
            owner.controller._session_api.api.stop_session(state['session_id'], reason='policy_complete')
            if index < 2:
                await self.wait_for(lambda: batch.index == index + 1)
        await asyncio.wait_for(batch.task, 3)
        self.assertEqual(batch.phase, 'complete')
        requests = self.apis[1].create_requests
        self.assertEqual([r['prompt'] for r in requests], ['first', 'second', 'third'])
        self.assertEqual(len({j['session_id'] for j in batch.jobs}), 3)
        for request in requests:
            self.assertEqual(request['runner_name'], 'Fixture Runner')
            self.assertEqual(request['email'], 'fixture@example.com')
            self.assertTrue(request['email_run_video'])
        status = (await self.call('/api/status', **browser))[1]
        self.assertEqual(status['prompt_batch']['phase'], 'complete')
        self.assertNotIn('batch-secret-key', json.dumps(status))
        self.assertNotIn('fixture@example.com', json.dumps(status['prompt_batch']))
        self.assertEqual(batch.payload, {})

    async def test_stop_cancels_pending_prompts_and_other_visitors_cannot_stop_it(self):
        browser, other = await self.session(), await self.session()
        self.assertEqual((await self.call('/api/run', method='POST', payload=self.payload(), **browser))[0], 200)
        owner = list(self.app.visitors.values())[0]
        self.assertEqual((await self.call('/api/stop', method='POST', **other))[0], 200)
        self.assertFalse(owner.prompt_batch.cancelled)
        self.assertEqual((await self.call('/api/run', method='POST', payload=self.payload(), **browser))[0], 409)
        await self.call('/api/stop', method='POST', **browser)
        await asyncio.wait_for(owner.prompt_batch.task, 3)
        self.assertEqual(owner.prompt_batch.phase, 'cancelled')
        self.assertEqual([j['status'] for j in owner.prompt_batch.jobs][1:], ['cancelled', 'cancelled'])
        self.assertEqual(len(self.providers), 1)

    async def test_documented_character_limit_accepts_escaped_unicode_prompts(self):
        browser = await self.session()
        prompts = ['🦾' * 4000] * 4  # 16,000 characters, 192,000 escaped JSON bytes.
        code, result, _ = await self.call('/api/run', method='POST',
            payload={**self.payload(), 'prompts':prompts}, **browser)
        self.assertEqual(code, 200, result)
        owner = next(iter(self.app.visitors.values()))
        self.assertEqual(owner.prompt_batch.jobs[0]['prompt'], prompts[0])
        await self.call('/api/stop', method='POST', **browser)
        await asyncio.wait_for(owner.prompt_batch.task, 3)

    async def test_invalid_batch_is_rejected_before_any_queue_or_provider_call(self):
        browser = await self.session()
        for prompts in ([], ['one'], ['okay', ' '], ['x', 42], ['x'] * 11, ['x' * 4000] * 5):
            code, _, _ = await self.call('/api/run', method='POST', payload={**self.payload(), 'prompts': prompts}, **browser)
            self.assertEqual(code, 400)
        self.assertFalse(self.providers)
        self.assertEqual((await self.call('/api/run', method='POST', payload=self.payload(), cookie=browser['cookie'], csrf='wrong'))[0], 403)

    async def test_concurrent_stop_during_provider_preparation_never_joins_a_queue(self):
        browser = await self.session()
        preparing, release = threading.Event(), threading.Event()
        original = self.app.provider_factory
        def factory(*args):
            preparing.set()
            if not release.wait(3):
                raise RuntimeError('Test did not release provider preparation')
            return original(*args)
        self.app.provider_factory = factory
        launch = asyncio.create_task(self.call('/api/run', method='POST', payload=self.payload(), **browser))
        try:
            self.assertTrue(await asyncio.to_thread(preparing.wait, 2))
            owner = next(iter(self.app.visitors.values()))
            stops = [asyncio.create_task(self.call('/api/stop', method='POST', **browser)) for _ in range(8)]
            await self.wait_for(lambda: owner.prompt_batch.cancelled)
            release.set()
            self.assertEqual((await launch)[0], 503)
            await asyncio.gather(*stops)
            self.assertFalse(self.apis[1].create_requests)
        finally:
            release.set()
            await launch

    async def test_batch_honors_configured_session_cap_and_unlimited_mode(self):
        browser = await self.session()
        owner = next(iter(self.app.visitors.values()))
        self.app.session_run_limit = 2
        self.assertEqual((await self.call('/api/run', method='POST', payload=self.payload(), **browser))[0], 429)
        self.assertFalse(self.providers)
        self.app.session_run_limit = None
        owner.launches = 20
        code, result, _ = await self.call('/api/run', method='POST', payload=self.payload(), **browser)
        self.assertEqual(code, 200, result)
        await self.call('/api/stop', method='POST', **browser)
        await asyncio.wait_for(owner.prompt_batch.task, 3)

    async def test_safety_stop_never_retries_or_starts_the_next_prompt(self):
        browser = await self.session()
        self.assertEqual((await self.call('/api/run', method='POST', payload=self.payload(), **browser))[0], 200)
        owner = next(iter(self.app.visitors.values()))
        api = owner.controller._session_api.api
        with api._lock:
            api._transition(api._record(owner.controller.status()['session_id']), 'safety_aborted')
        await asyncio.wait_for(owner.prompt_batch.task, 3)
        self.assertEqual(owner.prompt_batch.phase, 'failed')
        self.assertEqual(len(self.providers), 1)

    async def test_time_limit_advances_to_the_next_prompt_without_retrying_the_first(self):
        browser = await self.session()
        self.assertEqual((await self.call('/api/run', method='POST', payload=self.payload(), **browser))[0], 200)
        owner = next(iter(self.app.visitors.values()))
        owner.last_launch -= 5
        api = owner.controller._session_api.api
        with api._lock:
            api._transition(api._record(owner.controller.status()['session_id']), 'timed_out')
        await self.wait_for(lambda: owner.prompt_batch.index == 1 and owner.controller.busy())
        self.assertEqual([r['prompt'] for r in api.create_requests], ['first', 'second'])
        await self.call('/api/stop', method='POST', **browser)
        await asyncio.wait_for(owner.prompt_batch.task, 3)
