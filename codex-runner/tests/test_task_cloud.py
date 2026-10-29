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
