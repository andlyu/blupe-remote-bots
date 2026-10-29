import unittest

import test_hosted
from remote_yam.controller_executor import ControllerExecutorPolicy, DREAM_MODEL, ROBOHOUSE


class ExecutorHostedTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    async def test_registered_controller_model_catalog_and_picker_asset_are_served(self):
        self.app.controller_models = {'custom': dict(provider='custom',model='custom',label='Your endpoint',
            available=True,custom=True,user_endpoint=True)}
        code,_,_ = await self.call('/static/controller-model-picker.js')
        self.assertEqual(code,200)
        browser = await self.session()
        code,result,_ = await self.call('/api/run',method='POST',payload=dict(provider='custom',model='my/model',
            prompt='Hold.',executor='controller',controller_model='custom',
            custom_endpoint=dict(protocol='responses_v1',url='https://inference.example/v1/responses')),**browser)
        self.assertEqual(code,200,result)
        self.assertFalse(self.providers)

    async def test_omitted_and_null_executor_use_existing_factory_and_queue(self):
        for extra in ({}, {'executor': None}):
            browser = await self.session()
            code, _, _ = await self.call('/api/run', method='POST', payload=dict(
                provider='openai', model='gpt-6.1-sol', api_key='private-key', prompt='task', **extra), **browser)
            self.assertEqual(code, 200)
        self.assertEqual(len(self.providers), 2)

    async def test_direct_route_queues_normally_without_hosted_dream_factory_or_key(self):
        self.app.robot_id = ROBOHOUSE
        self.app.extra_providers['dream'] = lambda *args: self.fail('Hosted Dream must not be constructed')
        browser = await self.session()
        code, _, _ = await self.call('/api/run', method='POST', payload=dict(
            provider='dream', model=DREAM_MODEL, prompt='task', executor='dream_one'), **browser)
        self.assertEqual(code, 200)
        visitor = list(self.app.visitors.values())[-1]
        self.assertIsInstance(visitor.controller._provider, ControllerExecutorPolicy)
        self.assertEqual(visitor.controller.status()['status'], 'queued')
        self.assertFalse(self.providers)

    async def test_wrong_robot_and_unknown_executor_are_rejected_before_queue(self):
        for executor in ('dream_one', 'unknown', ''):
            browser = await self.session()
            code, _, _ = await self.call('/api/run', method='POST', payload=dict(
                provider='dream', model=DREAM_MODEL, prompt='task', executor=executor), **browser)
            self.assertEqual(code, 400)
        self.assertFalse(self.providers)
