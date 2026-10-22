import json
import unittest
from remote_yam.past_runs import PastRuns


class HistoryTests(unittest.TestCase):
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
