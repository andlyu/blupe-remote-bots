import unittest
import json

import test_hosted
from remote_yam.controller_executor import ControllerExecutorPolicy, DREAM_MODEL, ROBOHOUSE


class ExecutorHostedTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    async def test_retired_aspire_offerings_are_hidden_without_changing_other_managed_models(self):
        async def setup(*args):
            return {'configured_providers': {
                'aspire': dict(model='gpt-6-astra', label='ASPIRE'),
                'hosted_aspire': dict(model='gpt-6-astra', label='Hosted ASPIRE'),
                'xlab': dict(model='existing', label='XLab')}}, []
        self.app.session_extension = setup
        code, result, _ = await self.call('/api/session', method='POST', payload={})
        self.assertEqual(code, 200)
        self.assertEqual(set(result['configured_providers']), {'xlab'})

    async def test_each_target_can_be_activated_without_restarting_other_model_routes(self):
        p = self.app.root/'controller-models.json'
        self.app.controller_models_file = str(p)
        spec = dict(provider='openai',model='gpt-6-astra',label='Astra',available=False,reason='Not activated')
        def save():
            p.write_text(json.dumps(dict(schema='blupe-controller-model-catalog-v1',robots={self.app.robot_id:{'astra':spec}})))
        save()
        self.assertFalse(self.app.controller_model_catalog()['astra']['available'])
        browser = await self.session()
        code, state, _ = await self.call('/api/status', **browser)
        self.assertEqual(code, 200)
        self.assertFalse(state['controller_models']['astra']['available'])
        spec['available'] = True;save()
        code, state, _ = await self.call('/api/status', **browser)
        self.assertEqual(code, 200)
        self.assertTrue(state['controller_models']['astra']['available'])
        code,result,_ = await self.call('/api/run',method='POST',payload=dict(provider='openai',model=spec['model'],
            prompt='Hold.',executor='controller',controller_model='astra'),**browser)
        self.assertEqual(code,200,result)
        self.assertFalse(self.providers)

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
