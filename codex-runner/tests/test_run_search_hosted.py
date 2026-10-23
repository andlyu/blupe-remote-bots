from urllib.parse import urlencode
from unittest.mock import Mock
import json
import unittest

import test_replay_link_hosted
from remote_yam.submission_log import SubmissionLog


class RunSearchHostedTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_replay_link_hosted.ReplayLinkTests.asyncSetUp
    asyncTearDown = test_replay_link_hosted.ReplayLinkTests.asyncTearDown
    call_replay = test_replay_link_hosted.ReplayLinkTests.call_replay

    async def test_real_archive_uses_the_configured_journal_without_exposing_contacts(self):
        self.app.submission_log = SubmissionLog(self.app.root / 'model-filter.sqlite3')
        journal = self.app.submission_log
        journal.record('dream', 'submitted', {'fields': {
            'model': 'Dream0', 'email': 'private@example.com', 'api_key': 'secret'}})
        journal.record('dream', 'stop_accepted', {'episode_id': 'ep_dream'})
        def read(path):
            if path == 'meta/blupe_source_episodes.jsonl':
                return '\n'.join(json.dumps({'episode_id': eid, 'episode_index': i,
                    'recorded_at': i}) for i, eid in enumerate(['ep_dream', 'ep_unknown']))
            if path == 'meta/episodes.jsonl':
                return '\n'.join(json.dumps({'episode_index': i, 'tasks': ['Move marker']})
                                 for i in range(2))
            return '' if path.startswith('meta/') else '{}'
        self.app.past_runs.reader = read
        code, body = await self.call_replay(b'model=Dream0&robot_id=yam-1')
        self.assertEqual(code, 200)
        self.assertEqual([r['episode_id'] for r in body['runs']], ['ep_dream'])
        self.assertEqual(body['runs'][0]['model'], 'Dream0')
        self.assertEqual(body['models'], ['Dream0', '__unrecorded__'])
        self.assertEqual(body['total'], 1)
        self.assertNotIn('private@example.com', json.dumps(body))
        self.assertNotIn('secret', json.dumps(body))

    async def test_model_filter_composes_with_search_robot_and_pagination(self):
        self.app.past_runs = Mock()
        self.app.past_runs.page.return_value = {'runs': [], 'total': 0, 'next_offset': None,
                                               'models': ['Dream0', 'Dream0 Flash']}
        code, body = await self.call_replay(urlencode({
            'model': 'Dream0', 'q': 'move marker', 'robot_id': 'yam-1', 'offset': 12}).encode())
        self.assertEqual(code, 200)
        self.app.past_runs.page.assert_called_once_with(
            12, query='move marker', robot_id='yam-1', model='Dream0')
        self.assertEqual(body['models'], ['Dream0', 'Dream0 Flash'])
        for model in ['x' * 129, 'Dream\x00zero']:
            self.app.past_runs.reset_mock()
            code, _ = await self.call_replay(urlencode({'model': model}).encode())
            self.assertEqual(code, 400)
            self.app.past_runs.page.assert_not_called()

    async def test_query_reaches_archive_with_public_outcome_and_replay(self):
        self.app.past_runs = Mock()
        self.app.past_runs.page.return_value = {'runs': [{'episode_id': 'ep_marker',
            'prompt': 'Pick up a marker', 'video_url': 'https://example.com/ep_marker.mp4',
            'search_match': {'exact': [], 'related': [{'query': 'pen', 'match': 'marker'}], 'partial': True}}],
            'total': 1, 'next_offset': None, 'stale': False}
        self.app.run_names.remember_result('ep_marker', {'provider': {'outcome': {
            'status': 'give_up', 'reason': 'The marker slipped out of the gripper.'}}})
        code, body = await self.call_replay(urlencode({'q': 'put pens in a cup', 'offset': 12}).encode())
        self.assertEqual(code, 200)
        self.app.past_runs.page.assert_called_once_with(12, query='put pens in a cup')
        self.assertEqual(body['runs'][0]['result'], 'Failure')
        self.assertEqual(body['runs'][0]['ending_reason'], 'The marker slipped out of the gripper.')
        self.assertIn('marker', body['runs'][0]['video_url'])

    async def test_empty_query_keeps_browse_and_oversize_query_is_bad_request(self):
        self.app.past_runs = Mock()
        self.app.past_runs.page.return_value = {'runs': [], 'next_offset': None}
        code, _ = await self.call_replay(b'q=+++')
        self.assertEqual(code, 200)
        self.app.past_runs.page.assert_called_once_with(0)
        self.app.past_runs.reset_mock()
        code, _ = await self.call_replay(urlencode({'q': 'x' * 301}).encode())
        self.assertEqual(code, 400)
        self.app.past_runs.page.assert_not_called()
