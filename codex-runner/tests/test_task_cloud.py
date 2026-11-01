import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from remote_yam.task_cloud import TaskCloud,task_key


class TaskCloudTests(unittest.TestCase):
    def test_cache_frozen_projection_independent_of_models_votes_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            calls=[]
            def encoder(texts):
                calls.append(texts)
                vectors={'place pens':[1,0,0,0], 'put pencils':[.98,.02,0,0],
                         'raise arms':[0,0,1,0], 'move apple':[0,1,0,0], 'new task':[0,0,0,1]}
                return np.array([vectors[t] for t in texts])
            rows=[{'prompt':p,'model':'M','episode_id':'ep_'+str(i)} for i,p in enumerate(['place pens','put pencils','raise arms','move apple'])]
            cloud=TaskCloud(Path(directory)/'map.sqlite3',encoder)
            first=cloud.index(rows)
            changed=[dict(row,model='Other',assessment={'incorrect':500}) for row in reversed(rows)]
            changed += [dict(rows[0],episode_id='ep_repeat'),{'prompt':'new task','episode_id':'ep_new'}]
            second=cloud.index(changed)
            self.assertEqual(first['version'],second['version'])
            for key,xyz in first['coordinates'].items(): self.assertEqual(xyz,second['coordinates'][key])
            self.assertEqual(calls[1],['new task'])
            self.assertEqual(len(second['coordinates']),5)
            restored=TaskCloud(cloud.path,lambda _:self.fail('cached task re-encoded'))
            self.assertEqual(restored.index(rows)['coordinates'],second['coordinates'])
            self.assertEqual(task_key(' Place  PENS '),task_key('place pens'))
            coords=first['coordinates']
            distance=lambda a,b: np.linalg.norm(np.array(coords[task_key(a)])-coords[task_key(b)])
            self.assertLess(distance('place pens','put pencils'),distance('place pens','raise arms'))

    def test_empty_snapshot_and_embedding_failures_do_not_publish_false_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            cloud=TaskCloud(Path(directory)/'map.sqlite3',lambda _:np.array([[float('nan')]*4]))
            rows=[{'prompt':'task'}]
            self.assertEqual(cloud.snapshot(rows)['status'],'indexing')
            with self.assertRaises(ValueError): cloud.index(rows)
            self.assertEqual(cloud.snapshot(rows)['coordinates'],{})
            self.assertEqual(cloud.snapshot([])['status'],'ready')


    def test_bundled_layout_is_immediate_and_keeps_previous_pca_for_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            cloud = TaskCloud(Path(directory)/'map.sqlite3')
            cloud.encode = lambda _: self.fail('seeded task was re-encoded')
            rows = [{'prompt':'Put the pens into the cup'}, {'prompt':'Put the pen into the cup'}]
            state = cloud.snapshot(rows)
            self.assertEqual(state['status'], 'ready')
            self.assertTrue(state['projection'].startswith('cosine-umap3-'))
            with cloud.database() as db:
                db.execute('INSERT INTO task_projections VALUES(?,?,?,?)',
                    ('legacy', 'centered-pca3-frozen-v1', 'old-map', '{}'))
                db.execute('INSERT INTO task_coordinates VALUES(?,?,?)', ('old-map', 'old-task', '[1,2,3]'))
                db.commit()
            cloud.index(rows)
            with cloud.database() as db:
                self.assertEqual(db.execute('SELECT xyz FROM task_coordinates WHERE version=?', ('old-map',)).fetchone()[0], '[1,2,3]')
            self.assertEqual(state['coordinates'], cloud.snapshot(rows)['coordinates'])

    def test_new_arrivals_are_finite_frozen_and_independent_of_arrival_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            def encode(texts):
                return np.asarray([[1 if i == (0 if text == 'arrival one' else 1) else 0
                                    for i in range(384)] for text in texts])
            one, two = {'prompt':'arrival one'}, {'prompt':'arrival two'}
            together = TaskCloud(Path(directory)/'together.sqlite3')
            together.encode = encode
            old = together.snapshot([])['coordinates']
            combined = together.index([one, two])
            for key, value in old.items():
                self.assertEqual(value, combined['coordinates'][key])
            separate = TaskCloud(Path(directory)/'separate.sqlite3')
            separate.encode = encode
            separate.index([two])
            individual = separate.index([one])
            for row in [one, two]:
                key = task_key(row['prompt'])
                self.assertTrue(np.isfinite(combined['coordinates'][key]).all())
                self.assertEqual(combined['coordinates'][key], individual['coordinates'][key])
            restored = TaskCloud(together.path)
            restored.encode = lambda _: self.fail('cached arrival re-encoded')
            self.assertEqual(combined['coordinates'], restored.index([one,two])['coordinates'])

    def test_corrupt_projection_cannot_publish_new_positions(self):
        from unittest.mock import patch
        from remote_yam.task_cloud import SEED
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = json.loads(SEED.read_text())
            seed['basis']['model_file'] = 'corrupt.joblib'
            (root/'seed.json').write_text(json.dumps(seed))
            (root/'corrupt.joblib').write_bytes(b'invalid artifact')
            with patch('remote_yam.task_cloud.SEED', root/'seed.json'):
                cloud = TaskCloud(root/'map.sqlite3')
                cloud.encode = lambda _: np.asarray([[1]+[0]*383])
                row = {'prompt':'unseen task'}
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    cloud.index([row])
                self.assertNotIn(task_key(row['prompt']), cloud.snapshot([row])['coordinates'])

    def test_zero_norm_embeddings_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cloud = TaskCloud(Path(directory)/'map.sqlite3', lambda _: np.zeros((1,384)))
            with self.assertRaisesRegex(ValueError, 'norm'):
                cloud.index([{'prompt':'invalid embedding'}])

    def test_transform_does_not_hold_the_index_write_lock(self):
        import sqlite3
        import threading
        with tempfile.TemporaryDirectory() as directory:
            cloud=TaskCloud(Path(directory)/'map.sqlite3')
            cloud.snapshot([])
            cloud.encode=lambda _: np.asarray([[1]+[0]*383])
            started,release=threading.Event(),threading.Event()
            class SlowProjection:
                def transform(self,vector):
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError('Test did not release transform')
                    return np.zeros((1,3))
            cloud.load_projector=lambda *args: SlowProjection()
            errors=[]
            def index():
                try: cloud.index([{'prompt':'slow new arrival'}])
                except Exception as exc: errors.append(exc)
            worker=threading.Thread(target=index)
            worker.start()
            try:
                self.assertTrue(started.wait(3))
                # A separate producer can publish while CPU work is paused.
                with sqlite3.connect(cloud.path,timeout=.1) as db:
                    db.execute('INSERT INTO task_embeddings VALUES(?,?,?)',('other','independent','[1]'))
                self.assertEqual(cloud.snapshot([])['status'],'ready')
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors,[])
            self.assertEqual(cloud.snapshot([{'prompt':'slow new arrival'}])['status'],'ready')

    def test_another_indexer_recovery_does_not_leave_ready_coordinates_in_error(self):
        with tempfile.TemporaryDirectory() as directory:
            cloud=TaskCloud(Path(directory)/'map.sqlite3')
            cloud.error=True
            self.assertEqual(cloud.snapshot([{'prompt':'Put the pens into the cup'}])['status'],'ready')
