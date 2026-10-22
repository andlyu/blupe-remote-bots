import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from remote_yam.past_runs import PastRuns
from remote_yam.run_history import run_models
from remote_yam.submission_log import SubmissionLog


class RunModelFilterTests(unittest.TestCase):
    def test_journal_projection_uses_exact_recorded_models_and_only_public_fields(self):
        with tempfile.TemporaryDirectory() as root:
            journal = SubmissionLog(Path(root) / 'journal.sqlite3')
            for submission, model, eid, event in [
                    ('one', 'Dream0', 'ep_old', 'lifecycle'),
                    ('two', 'Dream0 Flash', 'ep_flash', 'stop_accepted'),
                    ('missing', None, 'ep_unknown', 'lifecycle'),
                    ('invalid', {'api_key': 'secret'}, 'ep_bad', 'lifecycle')]:
                journal.record(submission, 'submitted', {'fields': {
                    'model': model, 'email': 'private@example.com', 'api_key': 'secret'}})
                journal.record(submission, event, {'episode_id': eid})
            journal.record('one', 'lifecycle', {'episode_id': 'ep_old'})
            journal.record('one', 'lifecycle', {'episode_id': '../private'})
            with sqlite3.connect(journal.path) as db:
                db.execute("INSERT INTO submissions(submission_id,event,details) VALUES ('one','lifecycle','invalid json')")
            self.assertEqual(run_models(journal.path), {'ep_old': 'Dream0', 'ep_flash': 'Dream0 Flash'})
            self.assertEqual(run_models(Path(root) / 'missing.sqlite3'), {})

    def test_full_archive_filtered_before_paging_and_composes_with_robot(self):
        reads = []
        def read(path):
            reads.append(path)
            if path == 'meta/blupe_source_episodes.jsonl':
                return '\n'.join(json.dumps({'episode_id': f'ep_{i}', 'episode_index': i,
                    'recorded_at': i, 'robot_id': 'other' if i == 0 else 'yam-1'}) for i in range(40))
            if path == 'meta/episodes.jsonl':
                return '\n'.join(json.dumps({'episode_index': i, 'tasks': [
                    'Move a marker' if i < 6 else 'Move a block']}) for i in range(40))
            if path.startswith('meta/'):
                return ''
            return '{}'
        models = {f'ep_{i}': 'Dream0' if i < 16 else 'Dream0 Flash' for i in range(39)}
        catalog = PastRuns(read, robot_id=None, model_reader=lambda: models)
        first = catalog.page(model='Dream0', robot_id='yam-1')
        self.assertEqual(first['total'], 15)
        self.assertEqual([r['episode_index'] for r in first['runs']], list(range(15, 3, -1)))
        self.assertEqual(first['next_offset'], 12)
        self.assertEqual(len([p for p in reads if p.startswith('episodes/')]), 12)
        self.assertEqual(first['models'], ['Dream0', 'Dream0 Flash', '__unrecorded__'])
        second = catalog.page(12, model='Dream0', robot_id='yam-1')
        self.assertEqual([r['episode_index'] for r in second['runs']], [3, 2, 1])
        self.assertIsNone(second['next_offset'])
        self.assertTrue(all(r['model'] == 'Dream0' for r in first['runs'] + second['runs']))
        self.assertEqual(catalog.page(model='Dream')['total'], 0)
        self.assertEqual(catalog.page(model='__unrecorded__')['runs'][0]['episode_id'], 'ep_39')
        self.assertEqual(catalog.page()['total'], 40)
        self.assertTrue(all('search_match' not in r for r in catalog.rows))
        self.assertTrue(all(r['model'] is None for r in catalog.rows))
        catalog.updated = 0
        def offline(path):
            raise OSError('offline')
        catalog.reader = offline
        saved = catalog.page(model='Dream0', robot_id='yam-1')
        self.assertTrue(saved['stale'])
        self.assertEqual(saved['total'], 15)

    def test_catalog_models_work_without_a_local_journal(self):
        def read(path):
            if path == 'meta/blupe_viewing.jsonl':
                return json.dumps({'episode_id': 'ep_preview', 'started_at': 2,
                    'model': 'Dream0', 'task': 'Move marker', 'preview': {'speed': 10}})
            if path == 'meta/blupe_source_episodes.jsonl':
                return json.dumps({'episode_id': 'ep_archived', 'episode_index': 1,
                    'recorded_at': 1, 'model': 'Dream0 Flash'})
            if path == 'meta/episodes.jsonl':
                return json.dumps({'episode_index': 1, 'tasks': ['Move marker']})
            if path.startswith('meta/'):
                return ''
            return '{}'
        catalog = PastRuns(read)
        self.assertEqual(catalog.page(model='Dream0')['runs'][0]['episode_id'], 'ep_preview')
        self.assertEqual(catalog.page(model='Dream0 Flash')['runs'][0]['episode_id'], 'ep_archived')

    def test_invalid_index_model_is_unrecorded_without_publishing_its_contents(self):
        def read(path):
            if path == 'meta/blupe_source_episodes.jsonl':
                return json.dumps({'episode_id': 'ep_bad', 'episode_index': 1, 'recorded_at': 1,
                                   'model': {'api_key': 'private'}})
            return '' if path.startswith('meta/') else '{}'
        page = PastRuns(read).page(model='__unrecorded__')
        self.assertEqual(page['total'], 1)
        self.assertIsNone(page['runs'][0]['model'])
        self.assertNotIn('private', json.dumps(page))
