import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from remote_yam.quick_replays import QuickReplays
from remote_yam.past_runs import PastRuns


class QuickReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.body=b'playable-preview';self.digest=hashlib.sha256(self.body).hexdigest()
        (self.root/'ep_saved').mkdir();(self.root/'ep_saved'/(self.digest+'.mp4')).write_bytes(self.body)
        self.meta=dict(episode_id='ep_saved',robot_id='robot',task='Put the duck on the plate',outcome='user_requested',
            bytes=len(self.body),started_at=1,ended_at=2,locally_ready_at=3,
            preview=dict(sha256=self.digest,duration_s=4,camera_order=['observer'],quality_stage='quick'))
        (self.root/'ep_saved.json').write_text(json.dumps(self.meta))
        self.store=QuickReplays(self.root)

    def test_same_host_lookup_never_waits_for_archive_or_loses_stopped_outcome(self):
        catalog=PastRuns(lambda _:self.fail('Archive read on fast lookup'),robot_id='robot')
        catalog.quick_replays=self.store
        row=catalog.get('ep_saved')
        self.assertEqual(row['result'],'Stopped')
        self.assertEqual(row['video_quality'],'quick')
        self.assertTrue(row['video_url'].endswith(self.digest+'.mp4'))

    def test_upgrade_is_visible_without_catalog_cache_expiry(self):
        self.meta['preview']['quality_stage']='final'
        (self.root/'ep_saved.json').write_text(json.dumps(self.meta))
        self.assertEqual(self.store.get('ep_saved')['video_quality'],'final')

    def test_range_requests_and_immutable_digest_validation(self):
        status,body,headers=self.store.video('ep_saved',self.digest,'bytes=2-5')
        self.assertEqual((status,body),(206,self.body[2:6]))
        self.assertIn((b'content-range',f'bytes 2-5/{len(self.body)}'.encode()),headers)
        self.assertEqual(self.store.video('ep_saved',self.digest,'bytes=-3')[1],self.body[-3:])
        self.assertEqual(self.store.video('ep_saved',self.digest,'bytes=999-')[0],416)
        (self.root/'ep_saved'/(self.digest+'.mp4')).write_bytes(b'changed')
        self.assertIsNone(self.store.video('ep_saved',self.digest))

    def test_robot_scope_and_path_validation(self):
        self.assertIsNone(self.store.get('ep_saved','other'))
        self.assertIsNone(self.store.get('../secret'))
        self.assertIsNone(self.store.video('../secret',self.digest))


if __name__=='__main__':unittest.main()


class QuickReplayHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_metadata_and_byte_range_through_real_asgi_boundary(self):
        import sys,shutil
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from playground import HostedRunner
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);body=b'recorded-video';digest=hashlib.sha256(body).hexdigest()
            (root/'ep_saved').mkdir();(root/'ep_saved'/(digest+'.mp4')).write_bytes(body)
            meta=dict(episode_id='ep_saved',robot_id='yam-1',task='Put the duck on the plate',outcome='user_requested',
                bytes=len(body),started_at=1,ended_at=2,locally_ready_at=3,
                preview=dict(sha256=digest,duration_s=4,camera_order=['observer'],quality_stage='quick'))
            (root/'ep_saved.json').write_text(json.dumps(meta))
            app=HostedRunner(public_origin='https://robot.example',session_api='https://session.example',camera_origin='https://session.example')
            app.past_runs.quick_replays=QuickReplays(root)
            app.past_runs.reader=lambda _:self.fail('Slow archive request on direct path')
            async def call(path,query=b'',extra=()):
                sent=[]
                async def receive():return {'type':'http.request','body':b''}
                async def send(message):sent.append(message)
                await app({'type':'http','method':'GET','path':path,'query_string':query,
                    'headers':[(b'host',b'robot.example'),*extra]},receive,send)
                return sent[0],b''.join(s.get('body',b'') for s in sent[1:])
            try:
                start,data=await call('/api/past-runs',b'episode_id=ep_saved&preview=1')
                self.assertEqual(start['status'],200)
                row=json.loads(data)['runs'][0];self.assertEqual(row['video_quality'],'quick')
                start,data=await call(row['video_url'],extra=[(b'range',b'bytes=0-3')])
                self.assertEqual((start['status'],data),(206,body[:4]))
                csp=dict(start['headers'])[b'content-security-policy']
                self.assertIn(b"media-src 'self'",csp)
            finally:shutil.rmtree(app.root,ignore_errors=True)
