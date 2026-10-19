import json
from pathlib import Path
import tempfile
import unittest
from remote_yam.submission_log import SubmissionLog
from remote_yam.run_history import history_ids
from remote_yam.past_runs import PastRuns


class HistoryTests(unittest.TestCase):
    def test_email_resolves_older_episodes_and_combines_browser_ids(self):
        with tempfile.TemporaryDirectory() as root:
            journal = SubmissionLog(Path(root)/'journal.sqlite3')
            for submission, email, eid in [('one','Person@Example.com','ep_older'), ('two','other@example.com','ep_other')]:
                journal.record(submission,'submitted',{'fields':{'email':email, 'api_key':'never-return'}})
                journal.record(submission,'lifecycle',{'episode_id':eid}, 'session')
            found = history_ids(journal.path,' person@example.com ', ['ep_browser'])
            self.assertEqual(found, {'ep_older','ep_browser'})
            self.assertEqual(history_ids(journal.path,'missing@example.com', []),set())
            self.assertEqual(history_ids(journal.path,'', ['ep_browser']), {'ep_browser'})
            with self.assertRaises(ValueError): history_ids(journal.path,'bad', [])
            with self.assertRaises(ValueError): history_ids(journal.path,'', ['../private'])

    def test_filter_runs_before_pagination_and_preserve_new_flow_playback(self):
        def read(path):
            if path == 'meta/blupe_viewing.jsonl':
                return '\n'.join(json.dumps({'episode_id':f'ep_{i}','started_at':i,'robot_id':'yam-1' if i%2 else 'other',
                    'task':'Task', 'preview':{'nominal_action_speed':10, 'processing':'main-flow-or-gripper-v1',
                    'duration_s':4.13,'camera_order':['observer','left','top','right']}}) for i in range(40))
            if path.startswith('meta/'): return ''
            return '{}'
        catalog = PastRuns(read,robot_id=None)
        first = catalog.page(episode_ids={f'ep_{i}' for i in range(40)},robot_id='yam-1')
        self.assertEqual(len(first['runs']),12)
        self.assertEqual(first['next_offset'],12)
        second = catalog.page(12,episode_ids={f'ep_{i}' for i in range(40)},robot_id='yam-1')
        self.assertEqual(len(second['runs']),8)
        self.assertIsNone(second['next_offset'])
        for row in first['runs']+second['runs']:
            self.assertEqual(row['robot_id'],'yam-1')
            self.assertTrue(row['compressed'])
            self.assertEqual(row['preview_speed'],10)
            self.assertEqual(row['video_duration_s'],4.13)
            self.assertEqual(row['camera_order'][0],'observer')
