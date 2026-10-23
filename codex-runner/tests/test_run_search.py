import json
import unittest

from remote_yam.past_runs import PastRuns
from remote_yam.run_search import rank_runs


class RunSearchTests(unittest.TestCase):
    def test_natural_task_finds_related_objects_and_partial_evidence(self):
        rows = [
            {'episode_id': 'unrelated', 'prompt': 'Put a block on the shelf'},
            {'episode_id': 'partial', 'prompt': 'Pick up the markers'},
            {'episode_id': 'related', 'prompt': 'Place a marker in the mug'},
            {'episode_id': 'exact', 'prompt': 'Put the pen into the cup'},
        ]
        result = rank_runs(rows, 'Will it be able to put pens into a cup?')
        self.assertEqual([row['episode_id'] for row in result], ['exact', 'related', 'partial'])
        self.assertFalse(result[0]['search_match']['partial'])
        self.assertTrue(result[-1]['search_match']['partial'])
        self.assertIn({'query': 'pen', 'match': 'marker'}, result[-1]['search_match']['related'])
        self.assertNotIn('search_match', rows[0])
        self.assertNotIn('search_match', rows[-1])

    def test_word_boundaries_inflections_case_and_literal_query(self):
        rows = [{'prompt': 'Picked up MARKERS'}, {'prompt': 'Open the gripper'}, {'prompt': 'Move glasses'}]
        self.assertEqual(len(rank_runs(rows, 'picking up marker')), 1)
        self.assertEqual(len(rank_runs(rows, 'cup')), 1)
        self.assertEqual(rank_runs(rows, 'pen'), [dict(rows[0], search_match={
            'exact': [], 'related': [{'query': 'pen', 'match': 'marker'}], 'partial': False})])
        for query in ['.*', 'the and can it', '<script>', 'unicorn']:
            self.assertEqual(rank_runs(rows, query), [])
        with self.assertRaises(ValueError):
            rank_runs(rows, 'x' * 301)

    def test_recent_first_ties_and_original_catalog_preserved(self):
        rows = [{'episode_id': str(i), 'prompt': 'Move a marker'} for i in [3, 2, 1]]
        self.assertEqual([r['episode_id'] for r in rank_runs(rows, 'pen')], ['3', '2', '1'])
        self.assertTrue(all('search_match' not in r for r in rows))

    def test_color_or_action_alone_cannot_match_a_different_object(self):
        rows = [{'prompt': 'Put a red block on the shelf'}, {'prompt': 'Pick up the blue marker'}]
        result = rank_runs(rows, 'put a red pen into a cup')
        self.assertEqual([r['prompt'] for r in result], ['Pick up the blue marker'])
        self.assertEqual(len(rank_runs(rows, 'red')), 1)

    def test_full_catalog_ranked_before_paging_and_only_page_details_loaded(self):
        reads = []
        def read(path):
            reads.append(path)
            if path == 'meta/blupe_source_episodes.jsonl':
                return '\n'.join(json.dumps({'episode_id': f'ep_{i}', 'episode_index': i,
                    'recorded_at': i, 'robot_id': 'other' if i == 0 else 'yam-1'}) for i in range(40))
            if path == 'meta/episodes.jsonl':
                return '\n'.join(json.dumps({'episode_index': i, 'tasks': [
                    'Place a marker in a mug' if i < 16 else 'Move a block']}) for i in range(40))
            if path.startswith('meta/'):
                return ''
            return '{}'
        catalog = PastRuns(read, robot_id=None)
        first = catalog.page(query='put pens in cup', robot_id='yam-1')
        self.assertEqual(first['total'], 15)
        self.assertEqual([r['episode_index'] for r in first['runs']], list(range(15, 3, -1)))
        self.assertEqual(first['next_offset'], 12)
        self.assertEqual(len([p for p in reads if p.startswith('episodes/')]), 12)
        second = catalog.page(12, query='put pens in cup', robot_id='yam-1')
        self.assertEqual([r['episode_index'] for r in second['runs']], [3, 2, 1])
        self.assertIsNone(second['next_offset'])
        self.assertTrue(all('search_match' not in r for r in catalog.rows))
        self.assertTrue(all('search_match' not in r for r in catalog.page()['runs']))
        self.assertEqual(catalog.page(query='unicorn')['total'], 0)
        self.assertEqual(catalog.page(query='   ')['total'], 40)
        catalog.updated = 0
        def offline(path):
            raise OSError('offline')
        catalog.reader = offline
        stale = catalog.page(query='pen', robot_id='yam-1')
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['total'], 15)


    def test_apple_search_finds_old_prompts_without_substring_false_matches(self):
        rows = [
            {'episode_id': 'ep_new', 'prompt': 'Move a block'},
            {'episode_id': 'ep_apple', 'prompt': 'Move the apple to the red chip'},
            {'episode_id': 'ep_poke', 'prompt': 'Poke apples with the thin black marker'},
            {'episode_id': 'ep_pineapple', 'prompt': 'Pick up the pineapple'},
        ]
        result = rank_runs(rows, 'apple')
        self.assertEqual([r['episode_id'] for r in result], ['ep_apple', 'ep_poke'])
        self.assertTrue(all(r['search_match']['exact'] == ['apple'] for r in result))
