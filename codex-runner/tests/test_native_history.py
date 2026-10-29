import asyncio
import hashlib
import io
import json
import shutil
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
from remote_yam.native_history import NativeFrames, NativePastRuns, render_replay
from remote_yam.run_assessments import RunAssessments
from remote_yam.task_cloud import TaskCloud
from remote_yam.session import MockSessionAPI
from station_playground import StationPlayground


def episode(root, eid='ep_local', *, prompt='Place apple on plate', model='recorded-model', status='finalized'):
    folder=root/eid; (folder/'images').mkdir(parents=True)
    rows=[]
    for index,stamp in enumerate((0.,.1,.5)):
        row=dict(frame_index=index,timestamp=stamp)
        for role,color in [('top','red'),('left','green'),('right','blue')]:
            name=f'images/{role}-{index:06d}.jpg'
            Image.new('RGB',(64,48),color).save(folder/name)
            row[role+'_image_path']=name
        rows.append(row)
    samples=''.join(json.dumps(row)+'\n' for row in rows)
    (folder/'samples.jsonl').write_text(samples)
    meta=dict(episode_id=eid,task=prompt,model=model,started_at=1,fps=10,rows=len(rows),
              status=status,outcome='policy_complete',samples_sha256=hashlib.sha256(samples.encode()).hexdigest())
    (folder/'manifest.json').write_text(json.dumps(meta))
    return folder


def fake_renderer(folder,meta,target):
    target.write_bytes(b'\0\0\0 ftypisom'+b'x'*128)
    return dict(duration=.6,camera_order=['top','left','right'],video_layout='observer-focus')


def archive_episode(folder):
    """Observed direct_usb_tar contract, preserving native relative member names."""
    with tarfile.open(folder/'images.tar','w') as archive:
        for path in sorted((folder/'images').glob('*.jpg')):
            archive.add(path,arcname='images/'+path.name)
    shutil.rmtree(folder/'images')
    meta=json.loads((folder/'manifest.json').read_text())
    meta.update(recording_storage='direct_usb_tar',images_archive='images.tar')
    (folder/'manifest.json').write_text(json.dumps(meta))
    return meta


class NativeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.episodes=self.root/'episodes';self.episodes.mkdir()
        self.cache=self.root/'cache'

    def test_metadata_does_not_prepare_or_expose_paths_then_lazy_detail_is_cached_across_restart(self):
        folder=episode(self.episodes)
        with patch('urllib.request.urlopen',side_effect=AssertionError('No hosted fallback')):
            catalog=NativePastRuns([self.episodes],self.cache,renderer=fake_renderer)
            data=catalog.page(metadata=True)
            self.assertEqual(data['total'],1);self.assertIsNone(catalog.worker)
            self.assertNotIn('video_url',data['runs'][0]);self.assertNotIn(str(self.root),json.dumps(data))
            detail=catalog.get('ep_local');self.assertEqual(detail['video_status'],'processing')
            catalog.queue.join();detail=catalog.get('ep_local')
            self.assertEqual(detail['video_status'],'ready');self.assertFalse(detail['compressed'])
            self.assertEqual(detail['original_video_url'],detail['video_url'])
            self.assertTrue(detail['video_url'].startswith('/api/native-runs/ep_local/'))
            restored=NativePastRuns([self.episodes],self.cache,renderer=lambda *a:self.fail('Reencoded unchanged recording'))
            self.assertEqual(restored.get('ep_local')['video_url'],detail['video_url'])
            self.assertEqual((folder/'samples.jsonl').read_text().count('\n'),3)

    def test_filters_use_recorded_models_and_finalization_receipt_starts_preparation_without_cache_wait(self):
        first=episode(self.episodes,status='recording')
        episode(self.episodes,'ep_other',prompt='Move blue block',model='other')
        catalog=NativePastRuns([self.episodes],self.cache,renderer=fake_renderer)
        self.assertEqual(catalog.page(metadata=True,models=['other'],query='blue')['total'],1)
        self.assertEqual(catalog.get('ep_local')['video_status'],'unavailable')
        meta=json.loads((first/'manifest.json').read_text());meta['status']='finalized'
        (first/'manifest.json').write_text(json.dumps(meta))
        self.assertEqual(catalog.get('ep_local')['video_status'],'processing')
        catalog.queue.join();self.assertEqual(catalog.get('ep_local')['video_status'],'ready')

    def test_links_escape_missing_and_malformed_records_are_not_catalogued_or_served(self):
        episode(self.episodes)
        (self.episodes/'ep_link').symlink_to(self.episodes/'ep_local',target_is_directory=True)
        bad=self.episodes/'ep_bad';bad.mkdir();(bad/'manifest.json').symlink_to(self.episodes/'ep_local/manifest.json')
        catalog=NativePastRuns([self.episodes],self.cache,renderer=fake_renderer)
        self.assertEqual(catalog.page(metadata=True)['total'],1)
        with self.assertRaises(ValueError):catalog.media_path('ep_absent','a'*64)
        catalog.get('ep_local');catalog.queue.join()
        detail=catalog.get('ep_local');key=detail['video_url'].rsplit('/',1)[1][:-4]
        target=catalog.media_path('ep_local',key);target.unlink();target.symlink_to(self.root/'private-key')
        (self.root/'private-key').write_text('private')
        with self.assertRaises(ValueError):catalog.media_path('ep_local',key)

    def test_failed_encoder_is_truthful_without_touching_recordings(self):
        folder=episode(self.episodes)
        before={p.relative_to(folder):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
        def failure(*args):raise FileNotFoundError('ffmpeg')
        catalog=NativePastRuns([self.episodes],self.cache,renderer=failure)
        catalog.get('ep_local');catalog.queue.join()
        detail=catalog.get('ep_local');self.assertEqual(detail['video_status'],'unavailable');self.assertIsNone(detail['video_url'])
        self.assertEqual(before,{p.relative_to(folder):p.read_bytes() for p in folder.rglob('*') if p.is_file()})

    def test_only_the_marked_reproducible_cache_is_bounded_and_evicted(self):
        episode(self.episodes)
        catalog=NativePastRuns([self.episodes],self.cache,renderer=fake_renderer)
        catalog.get('ep_local');catalog.queue.join()
        episode(self.episodes,'ep_second');catalog.updated=0
        with patch('remote_yam.native_history.CACHE_BYTES',200):
            catalog.get('ep_second');catalog.queue.join()
        self.assertLessEqual(sum(p.stat().st_size for p in self.cache.glob('*.mp4')),200)
        self.assertTrue((self.episodes/'ep_local/samples.jsonl').is_file())
        unsafe=self.root/'not-a-cache';unsafe.mkdir();(unsafe/'private.txt').write_text('Keep')
        with self.assertRaises(ValueError):NativePastRuns([self.episodes],unsafe)
        self.assertEqual((unsafe/'private.txt').read_text(),'Keep')

    def test_overlapping_candidate_cannot_remove_active_encode_output(self):
        folder=episode(self.episodes)
        started=threading.Event();finish=threading.Event()
        def slow_renderer(folder,meta,target):
            fake_renderer(folder,meta,target);started.set();finish.wait(3)
            self.assertTrue(target.is_file())
            return dict(duration=.6,camera_order=['top','left','right'],video_layout='observer-focus')
        first=NativePastRuns([self.episodes],self.cache,renderer=slow_renderer)
        second=NativePastRuns([self.episodes],self.cache,renderer=lambda *a:self.fail('Concurrent encoder'))
        first.get('ep_local');self.assertTrue(started.wait(2))
        second.get('ep_local');second.queue.join();finish.set();first.queue.join()
        self.assertEqual(second.get('ep_local')['video_status'],'ready')

    def test_tar_boundaries_reject_links_traversal_duplicates_oversize_and_missing_frames(self):
        folder=episode(self.episodes);meta=archive_episode(folder)
        for name,kind,size in [('../private.jpg',tarfile.REGTYPE,1),
                ('images/top-000000.jpg',tarfile.SYMTYPE,0),
                ('images/top-000000.jpg',tarfile.LNKTYPE,0),
                ('images/top-000000.jpg',tarfile.REGTYPE,8*1024*1024+1)]:
            with self.subTest(name=name,kind=kind,size=size):
                member=tarfile.TarInfo(name);member.type=kind;member.size=size;member.linkname='/private.jpg'
                with tarfile.open(folder/'images.tar','w') as archive:
                    archive.addfile(member,io.BytesIO(b'x'*size) if size else None)
                with self.assertRaises(ValueError):NativeFrames(folder,meta)
        with tarfile.open(folder/'images.tar','w') as archive:
            for _ in range(2):
                member=tarfile.TarInfo('images/top-000000.jpg');member.size=1
                archive.addfile(member,io.BytesIO(b'x'))
        with self.assertRaises(ValueError):NativeFrames(folder,meta)
        with tarfile.open(folder/'images.tar','w'):pass
        with NativeFrames(folder,meta) as frames:
            with self.assertRaises(ValueError):frames.open('images/top-000000.jpg','top')
        for value in ('../private.tar','/private.tar'):
            with self.assertRaises(ValueError):NativeFrames(folder,{**meta,'images_archive':value})
        (folder/'images.tar').unlink();(folder/'images.tar').symlink_to(self.root/'private.tar')
        with self.assertRaises(ValueError):NativeFrames(folder,meta)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Requires actual H.264 tools')
    def test_real_h264_encode_retains_recorded_pause_and_only_reads_allowlisted_images(self):
        folder=episode(self.episodes);target=self.root/'real.mp4'
        info=render_replay(folder,json.loads((folder/'manifest.json').read_text()),target)
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]))
        self.assertEqual(probe['streams'][0]['codec_name'],'h264')
        self.assertAlmostEqual(float(probe['format']['duration']),.6,places=2)
        self.assertEqual(info['duration'],.6)
        rows=[json.loads(line) for line in (folder/'samples.jsonl').read_text().splitlines()]
        rows[0]['top_image_path']='../../private.jpg'
        (folder/'samples.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        meta=json.loads((folder/'manifest.json').read_text());meta.pop('samples_sha256')
        with self.assertRaises(ValueError):render_replay(folder,meta,self.root/'denied.mp4')

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'Requires actual H.264 tools')
    def test_direct_usb_tar_replay_matches_loose_jpegs_with_one_readonly_archive_open(self):
        folder=episode(self.episodes);loose=self.root/'loose.mp4'
        render_replay(folder,json.loads((folder/'manifest.json').read_text()),loose)
        meta=archive_episode(folder)
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
        original_open=tarfile.open
        with patch('remote_yam.native_history.tarfile.open',wraps=original_open) as opened:
            info=render_replay(folder,meta,self.root/'archive.mp4')
        self.assertEqual(opened.call_count,1);self.assertEqual(opened.call_args.kwargs['mode'],'r:')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(self.root/'archive.mp4')]))
        self.assertEqual(probe['streams'][0]['codec_name'],'h264')
        self.assertEqual(info['duration'],.6)
        def decoded(path):
            return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        self.assertEqual(decoded(loose),decoded(self.root/'archive.mp4'))
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()})
        self.assertFalse((folder/'images').exists())


class NativeAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.episodes=self.root/'episodes';self.episodes.mkdir();episode(self.episodes)
        self.api=MockSessionAPI(auto_activate=False);self.app=self.make_app()
        self.cookie='';self.csrf=''

    def make_app(self):
        return StationPlayground(public_origin='http://127.0.0.1:8787',session_api='http://127.0.0.1:8000',
            camera_origin='http://127.0.0.1:8089',recording_root=self.root/'state',episode_roots=[self.episodes],
            native_renderer=fake_renderer,api_factory=lambda:self.api,hardware_control=False)

    async def asyncTearDown(self):
        self.app.past_runs.queue.join()
        for visitor in self.app.visitors.values():visitor.close()
        self.temp.cleanup()

    async def call(self,path,payload=None,*,query='',extra=()):
        messages=[]
        headers=dict([(b'host',b'127.0.0.1:8787'),(b'origin',b'http://127.0.0.1:8787'),
            (b'content-type',b'application/json'),(b'cookie',self.cookie.encode()),(b'x-yam-runner-token',self.csrf.encode()),*extra])
        scope=dict(type='http',path=path,method='POST' if payload is not None else 'GET',headers=list(headers.items()),query_string=query.encode())
        async def receive():return dict(type='http.request',body=json.dumps(payload or {}).encode())
        async def send(message):messages.append(message)
        with patch('remote_yam.subscription_setup.subscription_status',return_value={'ready':False,'state':'login_required','message':'Not signed in'}):
            await self.app(scope,receive,send)
        response=messages[0];h=dict(response['headers'])
        if b'set-cookie' in h:self.cookie=h[b'set-cookie'].decode().split(';')[0]
        body=b''.join(m.get('body',b'') for m in messages[1:])
        return response['status'],json.loads(body) if b'application/json' in h.get(b'content-type',b'') else body,h

    async def test_native_catalog_details_range_media_and_privacy_boundaries_without_any_network_or_queue(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No public history, camera, or control call')):
            code,page,headers=await self.call('/')
            self.assertEqual(code,200);self.assertIn(b'id="past-runs"',page);self.assertNotIn(b'id="past-runs" hidden',page)
            self.assertIn(b"media-src 'self' blob:",headers[b'content-security-policy'])
            code,catalog,_=await self.call('/api/run-catalog',query='view=table&robot_id=yam-1')
            self.assertEqual(code,200);self.assertEqual(catalog['source'],'native');self.assertEqual(catalog['total'],1)
            self.assertEqual(catalog['scores'][0]['denominator'],0)
            self.assertFalse(self.app.visitors)
            await asyncio.to_thread(self.app.past_runs.queue.join)
            code,detail,_=await self.call('/api/past-runs',query='episode_id=ep_local')
            media=detail['runs'][0]['video_url'];self.assertTrue(media.startswith('/api/native-runs/'))
            code,body,h=await self.call(media,extra=[(b'range',b'bytes=0-15')])
            self.assertEqual((code,len(body)),(206,16));self.assertEqual(h[b'accept-ranges'],b'bytes')
            self.assertEqual((await self.call(media,extra=[(b'range',b'bytes=999999-')]))[0],416)
            self.assertEqual((await self.call(media,extra=[(b'host',b'other.example')]))[0],421)
            self.assertEqual((await self.call(media,extra=[(b'origin',b'https://other.example')]))[0],403)
            self.assertEqual((await self.call('/api/run-catalog',extra=[(b'sec-fetch-site',b'cross-site')]))[0],403)
            for denied in ('/synchronized/index.m3u8','/live-video/top','/api/recordings/run_fake/artifacts'):
                self.assertEqual((await self.call(denied))[0],404)
        self.assertEqual(self.api.create_requests,[])

    async def test_assessments_persist_for_same_native_user_and_hollow_votes_do_not_move_xyz(self):
        _,session,_=await self.call('/api/session',{});self.csrf=session['csrf']
        visitor=next(iter(self.app.visitors.values()))
        self.app.run_assessments.register('ep_local',visitor.assessment_session,self.app.assessment_user(visitor),ended=True)
        code,assessment,_=await self.call('/api/run-assessment',{'episode_id':'ep_local','operation':'assess','label':'Success','revision':0})
        self.assertEqual((code,assessment['label']),(200,'Success'))
        # New browser can edit through the server's recorded local identity;
        # votes are still per-session and exclude without altering the label.
        self.cookie=self.csrf='';_,session,_=await self.call('/api/session',{});self.csrf=session['csrf']
        code,assessment,_=await self.call('/api/run-assessment',{'episode_id':'ep_local','operation':'vote','revision':1,'vote':-1})
        self.assertEqual((code,assessment['label'],assessment['eligibility']),(200,'Success','excluded'))
        import numpy as np
        self.app.task_cloud=TaskCloud(self.root/'map.sqlite3',lambda texts:np.ones((len(texts),4)))
        self.app.task_cloud.index(self.app.past_runs.page(metadata=True)['runs'])
        _,excluded,_=await self.call('/api/run-catalog',query='view=cloud')
        self.assertEqual(excluded['scores'][0]['denominator'],0);xyz=excluded['runs'][0]['xyz']
        await self.call('/api/run-assessment',{'episode_id':'ep_local','operation':'vote','revision':1,'vote':None})
        _,included,_=await self.call('/api/run-catalog',query='view=cloud')
        self.assertEqual((included['scores'][0]['successes'],included['scores'][0]['denominator']),(1,1))
        self.assertEqual(included['runs'][0]['xyz'],xyz)
        previous_user=self.app.assessment_user(visitor)
        for previous in self.app.visitors.values(): previous.close()
        self.app=self.make_app();self.cookie=self.csrf=''
        self.assertEqual(self.app.assessment_user(None),previous_user)
        _,session,_=await self.call('/api/session',{});self.csrf=session['csrf']
        code,assessment,_=await self.call('/api/run-assessment',{'episode_id':'ep_local','operation':'assess','label':'Failure','revision':1})
        self.assertEqual((code,assessment['revision'],assessment['history'][1]['label']),(200,2,'Success'))
