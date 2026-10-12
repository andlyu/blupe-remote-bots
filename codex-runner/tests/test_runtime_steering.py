"""Run ownership, ordered user turns, stale inference and real transport tests."""
import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_hosted as hosted_fixture
import test_codex_policy as codex_fixture
from test_robocurve_policy import Cameras, observation, response, finished
from remote_yam.anthropic_policy import messages_payload
from remote_yam.controller import RunnerController
from remote_yam.providers import PolicyComplete
from remote_yam.robocurve_policy import OpenAIAdapter
from remote_yam.session import MockSessionAPI
from remote_yam.steering import SteeringInbox, SteeringError


def make_provider():
    return OpenAIAdapter('test-key', 'gpt-6-astra', camera_source=Cameras())


def move(targets, call_id):
    return response('move_to', {'targets': targets, 'note': 'Move the requested gripper'}, call_id)


class InboxTests(unittest.TestCase):
    def test_shared_steering_preserves_text_but_omits_private_metadata(self):
        from remote_yam.public_conversation import project_events
        from remote_yam.conversation_publisher import ConversationPublisher
        from test_conversation_publisher import PublishingAPI
        rows = project_events([dict(id=1, timestamp=1, kind='steering_queued',
            message='Use left arm', details={'steering_id':1, 'request_id':'private-retry-id',
                                           'session_capability':'private-capability'})], 'run_test')
        self.assertEqual(rows[0]['message'], 'Use left arm')
        self.assertNotIn('private-', json.dumps(rows))
        api = PublishingAPI()
        publisher = ConversationPublisher(api, 'session', 'Model', 'Goal',
                                          secrets=('private-key',), interval=.01)
        publisher.add('steering_queued', 'Use left arm private-key', request_id='private-retry-id')
        publisher.close()
        publisher._thread.join(2)
        self.assertFalse(publisher._thread.is_alive())
        messages = api.shared[-1][1]['messages']
        self.assertEqual(messages[-1], {'role':'user', 'content':'Use left arm [redacted]'})
        self.assertNotIn('private-', json.dumps(messages))

    def test_concurrent_retries_are_idempotent_and_order_is_preserved(self):
        events = []
        inbox = SteeringInbox(lambda *args, **kwargs: events.append((args, kwargs)))
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(lambda _: inbox.submit('left arm only', 'request_000000001'), range(8)))
        self.assertTrue(all(row['id'] == 1 for row in rows))
        with patch('remote_yam.steering.time.monotonic', return_value=10**12):
            inbox.submit('then lift', 'request_000000002')
        history = []
        inbox.include(history)
        inbox.include(history)
        self.assertEqual(len(history), 3)
        self.assertEqual([x['role'] for x in history], ['system', 'user', 'user'])
        self.assertIn('left arm only', history[1]['content'])
        self.assertIn('then lift', history[2]['content'])
        self.assertEqual(len(events), 4)
        self.assertFalse(inbox.pending())

    def test_validation_rate_limits_and_bounded_pending(self):
        inbox = SteeringInbox(lambda *args, **kwargs: None)
        for text in ('', ' ', None, {}, 'x' * 2001):
            with self.assertRaises(SteeringError):
                inbox.submit(text, 'request_000000001')
        with self.assertRaises(SteeringError):
            inbox.submit('left', '../invalid')
        inbox.submit('left', 'request_000000001')
        with self.assertRaisesRegex(SteeringError, 'already used'):
            inbox.submit('right', 'request_000000001')
        with self.assertRaisesRegex(SteeringError, 'Wait a moment'):
            inbox.submit('right', 'request_000000002')
        for i in range(2, 9):
            with patch('remote_yam.steering.time.monotonic', return_value=10**12 + i * 2):
                inbox.submit('right', f'request_{i:09d}')
        with self.assertRaisesRegex(SteeringError, 'queued steering'):
            inbox.submit('left', 'request_000000009')
        self.assertTrue(all(x['state'] == 'not_delivered' for x in inbox.snapshot(active=False)))


class PromptTests(unittest.TestCase):
    def test_controller_submits_only_corrected_packet_and_keeps_same_lease(self):
        provider = make_provider()
        class LiveFeedbackSession(MockSessionAPI):
            def get_session(self, session_id):
                state = super().get_session(session_id)
                state.update(latest_observation_step=0,
                             lease_id=self._record(session_id)['lease_id'])
                return state
            def get_robot_observation(self, robot_id):
                return {**super().get_robot_observation(robot_id), **observation()}
        api = LiveFeedbackSession(observations=[observation()])
        controller = RunnerController(api)
        self.addCleanup(controller.disconnect)
        requests = []
        def infer(payload):
            requests.append(copy.deepcopy(payload))
            if len(requests) == 1:
                controller.steer(controller.status()['attempt_id'], 'Use right gripper', 'request_000000001')
                return move({'left_gripper': .2}, 'old')
            if len(requests) == 2:
                return move({'right_gripper': .8}, 'corrected')
            return response('done', {'summary':'finished', 'hindsight':''}, 'done')
        with patch.object(provider, '_post_json', side_effect=infer):
            original = controller.join(provider, 'Original goal')
            for _ in range(100):
                controller.update_monitor_observation(api.get_robot_observation('yam-1'))
                controller.process_next_event(.01)
                if controller.status()['status'] == 'stopped':
                    break
        self.assertEqual(controller.status()['status'], 'stopped')
        self.assertEqual(controller.status()['session_id'], original['session_id'])
        self.assertEqual(len(api.create_requests), 1)
        self.assertEqual(len(api.trajectory_log), 1)
        self.assertEqual(provider.steering.snapshot()[0]['state'], 'included')
        self.assertEqual(provider._calls, 3)

    def test_correction_follows_observation_and_preserves_goal_and_tool_feedback(self):
        provider, obs, requests = make_provider(), observation(), []
        def infer(payload):
            requests.append(copy.deepcopy(payload))
            return move({'left_gripper': .9}, f'call_{len(requests)}')
        with patch.object(provider, '_post_json', side_effect=infer):
            points = provider.build_trajectory('Original goal', obs, 0)
            provider.steering.submit('Use the right arm instead', 'request_000000001')
            with self.assertRaisesRegex(RuntimeError, 'before its motion completes'):
                provider.build_trajectory('Original goal', obs, 0)
            self.assertTrue(provider.steering.pending())
            final = finished(obs, points)
            provider.trajectory_completed(final, len(points))
            provider.build_trajectory('Original goal', final, len(points))
        history = requests[1]['input']
        self.assertEqual(history[1]['content'], 'Goal: Original goal')
        self.assertEqual(history[-1]['role'], 'user')
        self.assertIn('Use the right arm instead', history[-1]['content'])
        self.assertTrue(any(item.get('type') == 'function_call_output' and 'completed' in item['output'] for item in history))
        self.assertIn('Current observation', history[-3]['content'][0]['text'])
        wire = messages_payload({**requests[1], 'input': [item for item in history
                                                       if item.get('type') != 'reasoning']})
        self.assertIn('Use the right arm instead', wire['messages'][-1]['content'][-1]['text'])
        self.assertEqual(provider._prompt, 'Original goal')

    def test_updates_during_inference_supersede_motion_and_terminal_responses(self):
        for old_response in (move({'left_gripper': .2}, 'old'),
                             response('done', {'summary': 'done', 'hindsight': ''})):
            with self.subTest(response=old_response):
                provider, requests = make_provider(), []
                def infer(payload):
                    requests.append(copy.deepcopy(payload))
                    if len(requests) == 1:
                        provider.steering.submit('Use the right arm', 'request_000000001')
                        return old_response
                    return move({'right_gripper': .8}, 'corrected')
                with patch.object(provider, '_post_json', side_effect=infer), patch.object(provider._geometry, 'build', wraps=provider._geometry.build) as build:
                    provider.build_trajectory('Original goal', observation(), 0)
                self.assertEqual(build.call_count, 1)
                self.assertEqual(build.call_args.args[0], {'right_gripper': .8})
                self.assertTrue(any(item.get('type') == 'function_call_output' and 'superseded' in item['output'] for item in requests[1]['input']))
                self.assertIn('Use the right arm', requests[1]['input'][-1]['content'])

    def test_codex_resume_receives_steering_without_restarting_the_thread(self):
        with patch('remote_yam.codex_policy.codex_status', return_value={'ready': True}):
            provider = codex_fixture.CheckAdapter()
        self.addCleanup(provider._workspace.cleanup)
        calls = []
        move = codex_fixture.decision('move_to', note='Close left gripper slightly')
        move['targets']['left_gripper'] = .8
        def execute(command, prompt, images):
            calls.append((command, prompt))
            return codex_fixture.events(move if len(calls) == 1 else codex_fixture.decision())
        obs = codex_fixture.check_observation()
        with patch.object(provider, '_execute', side_effect=execute):
            points = provider.build_trajectory('task', obs, 0)
            final = finished(obs, points)
            provider.trajectory_completed(final, len(points))
            provider.steering.submit('We are finished; verify the placement', 'request_000000001')
            with self.assertRaises(PolicyComplete):
                provider.build_trajectory('task', final, len(points))
        self.assertEqual(calls[1][0][1:4], ['exec', 'resume', codex_fixture.THREAD])
        self.assertIn('Run-owner steering update', calls[1][1])
        self.assertIn('verify the placement', calls[1][1])


class SteeringHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = hosted_fixture.HostedTests.asyncSetUp
    asyncTearDown = hosted_fixture.HostedTests.asyncTearDown
    call = hosted_fixture.HostedTests.call
    session = hosted_fixture.HostedTests.session

    async def start_owner(self):
        browser = await self.session()
        visitor = list(self.app.visitors.values())[-1]
        provider = make_provider()
        controller = visitor.controller
        controller.join(provider, 'Original goal')
        controller._session_api.activate(controller._session_id)
        for _ in range(10):
            controller.process_next_event(.1)
            if controller.status()['status'] == 'running':
                break
        self.assertEqual(controller.status()['status'], 'running')
        return browser, controller, provider

    async def test_owner_csrf_origin_and_attempt_are_required(self):
        owner, controller, provider = await self.start_owner()
        spectator = await self.session()
        body = dict(attempt_id=controller.status()['attempt_id'], text='left arm only', request_id='request_000000001')
        checks = [({}, 401), ({**owner, 'csrf':'bad'}, 403),
                  ({**owner, 'origin':'https://evil.example'}, 403), (spectator, 409)]
        for browser, expected in checks:
            code, _, _ = await self.call('/api/steer', method='POST', payload=body, **browser)
            self.assertEqual(code, expected)
        self.assertFalse(provider.steering.pending())
        bad = dict(body, attempt_id='old-attempt')
        self.assertEqual((await self.call('/api/steer', method='POST', payload=bad, **owner))[0], 409)
        for _ in range(2):
            code, data, _ = await self.call('/api/steer', method='POST', payload=body, **owner)
            self.assertEqual(code, 200, data)
            self.assertEqual(data['message']['id'], 1)
        self.assertEqual(len(provider.steering.snapshot()), 1)
        self.assertEqual((await self.call('/api/status', **spectator))[1]['steering']['messages'], [])
        controller.stop()
        self.assertEqual(controller.status()['steering']['messages'][0]['state'], 'not_delivered')
        controller.disconnect()
        self.assertIsNone(controller._provider)
        self.assertEqual(controller.status()['steering']['messages'][0]['state'], 'not_delivered')
        self.assertEqual((await self.call('/api/steer', method='POST', payload=body, **owner))[0], 409)
        controller.join(make_provider(), 'New goal')
        self.assertEqual(controller.status()['steering']['messages'], [])
        self.assertEqual((await self.call('/api/steer', method='POST', payload=body, **owner))[0], 409)

    async def test_invalid_input_deadline_and_unsupported_policies(self):
        owner, controller, provider = await self.start_owner()
        body = dict(attempt_id=controller.status()['attempt_id'], text=' ', request_id='request_000000001')
        self.assertEqual((await self.call('/api/steer', method='POST', payload=body, **owner))[0], 400)
        body['text'] = 'left'
        provider.supports_runtime_steering = False
        self.assertEqual((await self.call('/api/steer', method='POST', payload=body, **owner))[0], 409)
        provider.supports_runtime_steering = True
        controller._run_started_at = 1
        self.assertEqual((await self.call('/api/steer', method='POST', payload=body, **owner))[0], 409)
        self.assertFalse(controller.status()['steering']['available'])
