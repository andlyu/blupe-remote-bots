import json
import unittest
from remote_yam.past_runs import PastRuns, RunNames, run_result
import tempfile
from pathlib import Path


class PastRunsTests(unittest.TestCase):
    def test_results_use_recorded_outcomes_and_never_guess_legacy_success(self):
        for outcome, expected in [('policy_complete', 'Success'), ('session_timeout', 'Stopped'), ('policy_runtime_timeout', 'Stopped'),
                                  ('physical_execution_failure', 'Failure'), ('user_requested', 'Stopped'),
                                  ('session_api_stop', 'Unknown'), (None, 'Unknown')]:
            self.assertEqual(run_result({'outcome': outcome})['result'], expected)
        catalog = PastRuns(lambda _: json.dumps({'outcome': 'session_timeout'}))
        _, detail = catalog._detail({'episode_id': 'ep_test'})
        self.assertEqual(detail['result'], 'Stopped')
        self.assertIn('time limit', detail['result_reason'])

    def test_zero_video_duration_is_distinct_from_missing_metadata(self):
        for meta, expected in [({'video': {'duration_s': 0}}, 0),
                               ({'preview': {'speed': 10, 'duration_s': 0}}, 0),
                               ({'rows': 0}, 0), ({}, None),
                               ({'video': {'duration_s': .01}}, .01),
                               ({'video': {'duration_s': -1}}, None)]:
            with self.subTest(meta=meta):
                catalog = PastRuns(lambda _: json.dumps(meta))
                _, detail = catalog._detail({'episode_id': 'ep_test'})
                self.assertEqual(detail['video_duration_s'], expected)

    def test_only_hash_matched_measured_checks_are_filtered(self):
        for kind, digest, hidden in [('arm_check','abc',True), ('arm_check','old',False), ('other','abc',False), ('unknown','abc',False)]:
            def read(path):
                if path.endswith('blupe_source_episodes.jsonl'):
                    return json.dumps({'episode_id':'ep_test','episode_index':137,'recorded_at':1,'samples_sha256':'abc'})
                if path.endswith('blupe_motion_classification.jsonl'):
                    return json.dumps({'episode_id':'ep_test','kind':kind,'version':1,'samples_sha256':digest})
                if path == 'meta/episodes.jsonl':
                    return json.dumps({'episode_index':137,'tasks':['Raise and lower both arms.']})
                return '{}'
            self.assertEqual(len(PastRuns(read).page()['runs']), 0 if hidden else 1)

    def test_missing_motion_index_keeps_raise_prompt_visible(self):
        def read(path):
            if path.endswith('blupe_source_episodes.jsonl'):
                return json.dumps({'episode_id':'ep_test','episode_index':1,'recorded_at':1})
            if path.endswith('blupe_motion_classification.jsonl'):
                raise OSError('missing')
            if path == 'meta/episodes.jsonl':
                return json.dumps({'episode_index':1,'tasks':['Raise and lower both arms.']})
            return '{}'
        self.assertEqual(len(PastRuns(read).page()['runs']), 1)

    def test_model_give_up_reason_is_preserved_instead_of_success(self):
        with tempfile.TemporaryDirectory() as root:
            names = RunNames(Path(root)/'names.sqlite3')
            state = {'provider': {'outcome': {'status':'give_up', 'reason':'I have no mechanism for eating.'}},
                     'interactions': {'events': [{'kind':'stop_requested','details':{'reason':'policy_complete'}}]}}
            names.remember_result('ep_test', state)
            result = names.results()['ep_test']
            self.assertEqual(result['result'], 'Failure')
            self.assertEqual(result['ending_reason'], 'I have no mechanism for eating.')
            self.assertIsNone(result['errors'])
            names.remember_result('ep_test', {'interactions':state['interactions']})
            self.assertEqual(names.results()['ep_test'], result)

    def test_accepted_model_ending_recovered_from_log_and_errors_separate(self):
        with tempfile.TemporaryDirectory() as root:
            names = RunNames(Path(root)/'names.sqlite3')
            names.remember_result('ep_test', {'error':'ValueError: invalid model response api_key=PRIVATE', 'interactions': {'events': [
                {'kind':'tool_result','details':{'result':{'status':'done','summary':'The apple is on the plate.'}}}]}})
            result = names.results()['ep_test']
            self.assertEqual(result['ending_reason'], 'The apple is on the plate.')
            self.assertEqual(result['errors'], 'ValueError: invalid model response api_key=[redacted]')
            self.assertNotIn('PRIVATE', json.dumps(result))

    def test_names_persist_across_catalog_instances(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'names.sqlite3'
            RunNames(path).remember('ep_test', 'Alex')
            self.assertEqual(RunNames(path).names(), {'ep_test': 'Alex'})
            RunNames(path).remember('ep_test', 'Different visitor')
            self.assertEqual(RunNames(path).names()['ep_test'], 'Alex')
    def test_failure_survives_restart_with_redacted_exception_text(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'names.sqlite3'
            RunNames(path).remember_result('ep_test', {'error': 'Provider error: malformed response api_key=SECRET'})
            result = RunNames(path).results()['ep_test']
            self.assertEqual(result['result'], 'Failure')
            self.assertNotIn('SECRET', json.dumps(result))
            RunNames(path).remember_result('ep_test', {'status': 'stopped'})
            self.assertEqual(RunNames(path).results()['ep_test'], result)

    def test_reported_success_and_cancellation_persist(self):
        with tempfile.TemporaryDirectory() as root:
            names = RunNames(Path(root)/'names.sqlite3')
            for reason, expected in [('policy_complete', 'Success'), ('user_requested', 'Cancelled')]:
                names.remember_result('ep_'+reason, {'interactions': {'events': [
                    {'kind': 'stop_requested', 'details': {'reason': reason}}]}})
                self.assertEqual(names.results()['ep_'+reason]['result'], expected)

    def test_public_projection_paging_preview_and_legacy(self):
        def read(path):
            if path.endswith('blupe_source_episodes.jsonl'):
                return '\n'.join(json.dumps({'episode_id': f'ep_{i}', 'episode_index': i, 'recorded_at': i}) for i in range(14))
            if path == 'meta/episodes.jsonl':
                return '\n'.join(json.dumps({'episode_index': i, 'tasks': [f'<script>task {i}</script>']}) for i in range(14))
            return json.dumps({'api_key': 'never public', 'preview': {'speed': 10, 'camera_order': ['top', 'observer', 'left', 'right']}}) if path.endswith('ep_13.json') else '{}'
        catalog = PastRuns(read)
        page = catalog.page()
        self.assertEqual(len(page['runs']), 12)
        self.assertEqual(page['next_offset'], 12)
        self.assertTrue(page['runs'][0]['compressed'])
        self.assertIn('/previews/ep_13.mp4', page['runs'][0]['video_url'])
        self.assertFalse(page['runs'][1]['compressed'])
        self.assertNotIn('api_key', json.dumps(page))
        self.assertEqual([r['episode_index'] for r in catalog.page(12)['runs']], [1, 0])

    def test_failed_refresh_retains_previous_results(self):
        catalog = PastRuns(lambda path: '')
        self.assertEqual(catalog.page()['runs'], [])
        catalog.updated = 0
        def failed(path): raise OSError('offline')
        catalog.reader = failed
        self.assertTrue(catalog.page()['stale'])

class ViewingFirstTests(unittest.TestCase):
    def test_catalog_hints_use_only_ready_index_media_without_episode_fetches(self):
        reads = []
        viewing = {'episode_id':'ep_ready', 'started_at':2, 'task':'Move block',
                   'api_key':'private', 'preview':{'speed':10, 'duration_s':2,
                    'camera_order':['top','left','right'], 'layout':'observer-focus', 'token':'private'}}
        def read(path):
            reads.append(path)
            if path == 'meta/blupe_viewing.jsonl':
                return json.dumps(viewing)
            if path.startswith('meta/'):
                return ''
            self.fail('Metadata catalog must not request episode files')
        catalog = PastRuns(read)
        row = catalog.page(metadata=True)['runs'][0]
        self.assertEqual(row['preview']['video_url'],
                         'https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/viewing/ep_ready.mp4')
        self.assertEqual(row['preview']['video_duration_s'],2)
        self.assertNotIn('private',json.dumps(row))
        for value in [0, -1, float('nan'), True, None]:
            catalog.viewing['ep_ready']['preview']['duration_s'] = value
            self.assertNotIn('preview',catalog.page(metadata=True)['runs'][0])

    def test_preview_visible_before_archive_then_deduplicated(self):
        viewing={'episode_id':'ep_new','started_at':2,'task':'Move block','outcome':'user_requested',
                 'preview':{'speed':10,'duration_s':2,'camera_order':['top','observer','left','right']}}
        archived=False
        def read(path):
            if path=='meta/blupe_viewing.jsonl':return json.dumps(viewing)
            if path=='meta/blupe_source_episodes.jsonl':
                return json.dumps(dict(episode_id='ep_new',episode_index=148,recorded_at=2)) if archived else ''
            if path=='meta/episodes.jsonl':return json.dumps(dict(episode_index=148,tasks=['Move block'])) if archived else ''
            if path=='meta/blupe_motion_classification.jsonl':return ''
            raise OSError('archive not yet uploaded')
        run=PastRuns(read).page()['runs'][0]
        self.assertIsNone(run['episode_index'])
        self.assertFalse(run['original_available'])
        self.assertIn('/viewing/',run['video_url'])
        self.assertEqual(run['video_duration_s'],2)
        archived=True
        runs=PastRuns(read).page()['runs']
        self.assertEqual(len(runs),1)
        self.assertTrue(runs[0]['original_available'])
        self.assertEqual(runs[0]['episode_index'],148)

class PublicRobotErrorTests(unittest.TestCase):
    def test_joint_error_is_numeric_and_persisted(self):
        from remote_yam.past_runs import public_robot_error
        text='Arm did not reach its target within 3s: left_joint_5 residual_rad=0.234303 measured_rad=0.349622 target_rad=0.583926; allowed_rad=0.100. PRIVATE'
        state={'safety_error':{'message':text}}
        shown=public_robot_error(state)
        self.assertIn('joint 5 (joint 6 of 6)',shown)
        self.assertIn('13.4° exceeds 5.7°',shown)
        self.assertNotIn('PRIVATE',shown)
        with tempfile.TemporaryDirectory() as root:
            names=RunNames(Path(root)/'names.sqlite3')
            names.remember_result('ep_test',state)
            self.assertEqual(names.results()['ep_test']['errors'],shown)
            names.remember_result('ep_test', {'error':'generic later error'})
            self.assertEqual(names.results()['ep_test']['errors'],shown)
        self.assertIsNone(public_robot_error({'error':'provider key SECRET'}))


def test_gripper_delta_error_is_exact_and_survives_generic_status(tmp_path):
    from remote_yam.past_runs import RunNames, public_robot_error
    message='ValueError: gripper delta limit at waypoint 0'
    assert public_robot_error({'error':message})==message
    assert public_robot_error({'safety_error':{'message':'gripper delta limit at waypoint 12'}})=='ValueError: gripper delta limit at waypoint 12'
    assert public_robot_error({'error':message+' secret token'}) is None
    names=RunNames(tmp_path/'names.db')
    names.remember_result('ep_test',{'error':message})
    names.remember_result('ep_test',{'error':'generic runner error'})
    row=names.results()['ep_test']
    assert row['result']=='Failure' and row['errors']==message and row['result_reason']==message


def test_explicit_three_cycle_prompt_hidden_for_archive_and_preview():
    def read(path):
        if path.endswith('blupe_source_episodes.jsonl'):
            return json.dumps({'episode_id':'ep_archived','episode_index':169,'recorded_at':1})
        if path=='meta/episodes.jsonl':
            return json.dumps({'episode_index':169,'tasks':['Raise and lower both arms for three cycles.']})
        if path.endswith('blupe_viewing.jsonl'):
            return '\n'.join(json.dumps({'episode_id':eid,'started_at':2,'task':prompt,'preview':{'duration_s':1}}) for eid,prompt in [('ep_preview','  Raise and lower both arms for three cycles. '),('ep_keep','Move the apple')])
        if path.endswith('blupe_motion_classification.jsonl'):return ''
        return '{}'
    assert [r['episode_id'] for r in PastRuns(read).page()['runs']] == ['ep_keep']


def test_robot_catalog_isolation_and_legacy_yam_default():
    def read(path):
        if path.endswith('blupe_source_episodes.jsonl'):
            return json.dumps({'episode_id':'ep_yam','episode_index':1,'recorded_at':1})
        if path == 'meta/episodes.jsonl':
            return json.dumps({'episode_index':1,'tasks':['Move YAM block']})
        if path.endswith('blupe_viewing.jsonl'):
            return json.dumps({'episode_id':'ep_maker','robot_id':'robot-maker','started_at':2,
                               'task':'Move SO101 block','original_available':True,
                               'preview':{'speed':10,'duration_s':2,'camera_order':['overhead','side','left','right']}})
        return '{}'
    assert [r['episode_id'] for r in PastRuns(read).page()['runs']] == ['ep_yam']
    result = PastRuns(read, robot_id='robot-maker').page()['runs']
    assert [r['episode_id'] for r in result] == ['ep_maker']
    assert result[0]['camera_order'] == ['overhead','side','left','right']
    assert result[0]['original_available'] is True
    assert PastRuns(read, robot_id='robot-other').page()['runs'] == []
    mixed = PastRuns(read, robot_id=None).page()['runs']
    assert [r['episode_id'] for r in mixed] == ['ep_maker', 'ep_yam']
    assert [r['robot_id'] for r in mixed] == ['robot-maker', 'yam-1']



class CatalogConcurrencyTests(unittest.TestCase):
    @staticmethod
    def catalog(reader):
        import time
        catalog=PastRuns(reader,robot_id=None)
        catalog.rows=[dict(episode_id='ep_slow',episode_index=1,robot_id='yam-1',
                           started_at=1,prompt='Lift slow block',model=None),
                      dict(episode_id='ep_fast',episode_index=2,robot_id='yam-1',
                           started_at=2,prompt='Lift fast block',model=None)]
        catalog.updated=time.monotonic()
        return catalog

    def test_slow_replay_does_not_block_eight_cached_catalog_reads(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor,wait
        entered,release=threading.Event(),threading.Event()
        def reader(path):
            self.assertEqual(path,'episodes/ep_slow.json')
            entered.set()
            if not release.wait(5):raise RuntimeError('Test did not release reader')
            return '{}'
        catalog=self.catalog(reader)
        with ThreadPoolExecutor(max_workers=9) as clients:
            replay=clients.submit(catalog.get,'ep_slow')
            try:
                self.assertTrue(entered.wait(2))
                readers=[clients.submit(catalog.page,metadata=True) for _ in range(8)]
                done,pending=wait(readers,timeout=1)
                self.assertFalse(pending,'A recording lookup must not hold the catalog lock')
                self.assertFalse(release.is_set())
                for result in done:
                    self.assertEqual([r['episode_id'] for r in result.result()['runs']],['ep_slow','ep_fast'])
            finally:
                release.set()
            self.assertEqual(replay.result()['episode_id'],'ep_slow')

    def test_concurrent_replays_share_fetch_without_blocking_other_episodes(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        entered,release=threading.Event(),threading.Event()
        calls=[]
        def reader(path):
            calls.append(path)
            if path=='episodes/ep_slow.json':
                entered.set()
                if not release.wait(5):raise RuntimeError('Test did not release reader')
            return '{"outcome":"policy_complete"}'
        catalog=self.catalog(reader)
        with ThreadPoolExecutor(max_workers=9) as clients:
            replays=[clients.submit(catalog.get,'ep_slow') for _ in range(8)]
            try:
                self.assertTrue(entered.wait(2))
                fast=clients.submit(catalog.get,'ep_fast')
                self.assertEqual(fast.result(timeout=1)['episode_id'],'ep_fast')
                self.assertFalse(release.is_set())
            finally:
                release.set()
            for result in replays:self.assertEqual(result.result()['result'],'Success')
        self.assertEqual(calls.count('episodes/ep_slow.json'),1)
        self.assertEqual(calls.count('episodes/ep_fast.json'),1)
        catalog.get('ep_slow');catalog.get('ep_fast')
        self.assertEqual(len(calls),2,'Cached details for both recordings remain available')
