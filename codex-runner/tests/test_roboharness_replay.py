"""Synthetic offline video artifacts; no hardware footage or motor/model requests."""
import io
import fcntl
import asyncio
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import Mock,patch,AsyncMock

from PIL import Image
from remote_yam.cameras import CameraFrame,CameraUnavailable
from remote_yam.integration_runs import PublicRunSource
from remote_yam.roboharness_replay import PublicCameraReplay,API

ROBOT='robot-ba8413962083809c'
EPISODE='ep_offline_replay'

class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(shutil.which('ffmpeg'),'The public replay release gate requires ffmpeg')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.clock=[1000.]
        self.publisher=PublicCameraReplay(self.root/'clips',robot_id=ROBOT)
        self.controller=Mock()
        def status():
            t=self.clock[0]-1000
            return {'attempt_id':'offline_attempt','status':'queued' if t<.3 else 'preparing' if t<.6 else 'running' if t<2.3 else 'completed',
                'episode_id':EPISODE if t>=.6 else None,'run_started_at':1000.6}
        self.controller.status.side_effect=status
        data=io.BytesIO();Image.new('RGB',(64,48),'red').save(data,format='JPEG')
        self.jpeg=data.getvalue()
        def capture(*args):
            self.clock[0]+=.02
            return CameraFrame('top',self.jpeg,self.clock[0],source_captured_at=self.clock[0]-.01)
        self.publisher.source.fetch=Mock(side_effect=capture)

    def follow(self):
        self.publisher.follow(self.controller,'offline_attempt',clock=lambda:self.clock[0],
            sleep=lambda seconds:self.clock.__setitem__(0,self.clock[0]+seconds))

    def source(self):
        database=self.root/'receipts.sqlite3'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE run_metadata (episode_id TEXT,robot_id TEXT,task TEXT,started_at REAL)')
            db.execute('INSERT INTO run_metadata VALUES (?,?,?,?)',(EPISODE,ROBOT,'Synthetic offline replay fixture',1000.6))
            db.execute('CREATE TABLE run_configuration (episode_id TEXT,configuration TEXT)')
            db.execute('INSERT INTO run_configuration VALUES (?,?)',(EPISODE,json.dumps({'model':'RoboHarness','email':'private@example.invalid'})))
        return PublicRunSource(database,self.publisher.root,ROBOT)

    def test_real_encoder_immutable_clip_range_reader_and_public_privacy(self):
        with patch('remote_yam.cameras.request.urlopen') as network:self.follow();network.assert_not_called()
        meta=json.loads((self.publisher.root/(EPISODE+'.json')).read_text())
        self.assertFalse(meta['capture_partial']);self.assertTrue(all(f['actual_image'] for f in meta['frames']))
        self.assertNotIn('email',json.dumps(meta));self.assertEqual(meta['preview']['speed'],1)
        source=self.source();clip=source.clip(EPISODE);self.assertIsNotNone(clip)
        self.assertNotIn('email',json.dumps(source.rows()))
        digest=clip['video_sha256'];status,body,headers=source.video(EPISODE,digest,'bytes=0-63')
        self.assertEqual(status,206);self.assertEqual(len(body),64);self.assertIn(b'ftyp',body)
        path=self.publisher.root/EPISODE/(digest+'.mp4')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_name,width,height','-of','json',str(path)],text=True))
        self.assertEqual(probe['streams'][0],{'codec_name':'h264','width':640,'height':520})
        self.assertTrue(any(x.args[0]=='replay_ready' for x in self.controller._interactions.add.call_args_list))

    def test_public_timeline_route_filters_unknown_fields_and_station(self):
        from types import SimpleNamespace
        from roboharness_playground import RoboHarnessPlayground
        self.follow();source=self.source()
        path=self.publisher.root/(EPISODE+'.json');metadata=json.loads(path.read_text())
        metadata['email']='private@example.invalid';metadata['preview']['email']='private@example.invalid'
        metadata['frames'][0]['email']='private@example.invalid';path.write_text(json.dumps(metadata))
        app=object.__new__(RoboHarnessPlayground);app.public_replays=self.publisher
        app.run_names=SimpleNamespace(path=source.database);app.robot_id=ROBOT;app.json=AsyncMock()
        scope=dict(method='GET',path='/api/roboharness/replay-evidence',query_string=('episode_id='+EPISODE).encode())
        asyncio.run(app.public_extension(scope,None,None,{}));self.assertEqual(app.json.call_args.args[1],200)
        self.assertNotIn('private@example.invalid',json.dumps(app.json.call_args.args[2]))
        app.robot_id='yam-1';asyncio.run(app.public_extension(scope,None,None,{}));self.assertEqual(app.json.call_args.args[1],404)

    def test_capture_gaps_and_missing_source_timestamp_are_explicit_partial_frames(self):
        original=self.publisher.source.fetch.side_effect;calls=[0]
        def capture(*args):
            calls[0]+=1
            if calls[0]==2:raise CameraUnavailable('top','Synthetic unavailable')
            if calls[0]==3:return CameraFrame('top',self.jpeg,self.clock[0],source_captured_at=None)
            return original(*args)
        self.publisher.source.fetch.side_effect=capture;self.follow()
        meta=json.loads((self.publisher.root/(EPISODE+'.json')).read_text())
        self.assertTrue(meta['capture_partial']);self.assertTrue(any(not f['actual_image'] for f in meta['frames']))
        self.assertTrue(all(f['source_captured_at'] is None for f in meta['frames'] if not f['actual_image']))
        self.assertTrue(self.source().clip(EPISODE)['capture_partial'])
        self.assertEqual(self.publisher.draw(None,1000).getpixel((320,200)),(16,21,27))

    def test_wrong_station_origin_and_changed_attempt_are_zero_camera_reads(self):
        for kwargs in ({'robot_id':'other'},{'robot_id':ROBOT,'origin':'https://untrusted.invalid'}):
            with self.assertRaises(ValueError):PublicCameraReplay(self.root,**kwargs)
        self.publisher.follow(self.controller,'other_attempt',clock=lambda:self.clock[0],sleep=lambda _:None)
        self.publisher.source.fetch.assert_not_called()
        self.assertFalse(list(self.publisher.root.glob('ep_*.json')))

    def test_encoder_failure_publishes_no_media_and_fixed_inline_diagnostic(self):
        failure=subprocess.CalledProcessError(1,['ffmpeg'],stderr=b'private diagnostic must not be exposed')
        with patch('remote_yam.roboharness_replay.StreamingCameraEncoder.finish',side_effect=failure):self.follow()
        self.assertFalse(list(self.publisher.root.rglob('*.mp4')));self.assertFalse(list(self.publisher.root.glob('ep_*.json')))
        events=self.controller._interactions.add.call_args_list
        self.assertTrue(any(e.args[0]=='replay_failed' for e in events));self.assertNotIn('private diagnostic',str(events))
        # Failed video preparation must retain the actual capture for recovery.
        self.assertTrue(list(self.publisher.root.rglob('*.jpg')))
        self.assertTrue(list(self.publisher.root.glob('.pending-*/*.json')))


    def test_long_clip_is_encoded_during_capture_with_actual_wall_clock_duration(self):
        import time
        import remote_yam.roboharness_replay as module
        original=module.StreamingCameraEncoder;writes=[];started=time.time()
        class ObservedEncoder(original):
            def write(encoder,data):writes.append(time.time());return super().write(data)
        def long_status():
            elapsed=time.time()-started
            return dict(attempt_id='offline_attempt',status='queued' if elapsed<.2 else 'preparing' if elapsed<.4 else 'running' if elapsed<33.4 else 'completed',episode_id=EPISODE if elapsed>=.4 else None,run_started_at=started+.4)
        self.controller.status.side_effect=long_status
        self.publisher.source.fetch.side_effect=lambda *args:CameraFrame('top',self.jpeg,time.time(),source_captured_at=time.time()-.01)
        # Exercise real two-Hz pacing. A synthetic burst of67 frames followed
        # by an artificial instant stop is not the deployed capture workload.
        with patch.object(module,'StreamingCameraEncoder',ObservedEncoder):
            self.publisher.follow(self.controller,'offline_attempt')
        meta=json.loads((self.publisher.root/(EPISODE+'.json')).read_text())
        self.assertGreater(len(writes),60);self.assertLess(writes[0]-started,5)
        self.assertEqual(meta['preview']['encoder_mode'],'streaming')
        video=self.publisher.root/EPISODE/(meta['preview']['sha256']+'.mp4')
        actual=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(video)],text=True))['format']['duration'])
        self.assertGreater(actual,30);self.assertAlmostEqual(actual,meta['preview']['duration_s'],places=2)
        self.assertTrue(all(0<=f['video_at']-f['source_captured_at']<=2 for f in meta['frames'] if f['actual_image']))
        self.assertFalse(list(self.publisher.root.glob('.pending-*')))

    def test_failed_finalize_retains_frames_and_recovery_never_reads_camera(self):
        with patch('remote_yam.roboharness_replay.StreamingCameraEncoder.finish',side_effect=subprocess.TimeoutExpired(['ffmpeg'],30)):
            self.follow()
        pending=list(self.publisher.root.glob('.pending-*'));self.assertEqual(len(pending),1)
        job=json.loads((pending[0]/'capture.json').read_text());self.assertEqual(job['capture_status'],'finished')
        self.assertEqual(job['preparation_status'],'retained_for_recovery')
        self.publisher.source.fetch.reset_mock()
        self.assertEqual(self.publisher.recover_pending(),[EPISODE]);self.publisher.source.fetch.assert_not_called()
        meta=json.loads((self.publisher.root/(EPISODE+'.json')).read_text())
        self.assertEqual(meta['preview']['encoder_mode'],'recovered_batch')
        self.assertFalse(meta['capture_partial']);self.assertFalse(pending[0].exists())

    def test_active_or_out_of_scope_recovery_manifest_is_not_consumed(self):
        self.publisher.root.mkdir(parents=True)
        work=self.publisher.root/'.pending-offline';work.mkdir()
        job=dict(episode_id=EPISODE,robot_id=ROBOT,model='RoboHarness',frames=[dict(file='000000.jpg',received_at=1000,actual_image=True,source_captured_at=1000)],capture_status='finished')
        (work/'capture.json').write_text(json.dumps(job))
        with (work/'.encode-lock').open('a+b') as lock,patch.object(self.publisher,'publish') as publish:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.publisher.recover_pending(),[]);publish.assert_not_called()
        for change in (dict(robot_id='another-robot'),dict(model='another-method'),dict(frames=[dict(file='../outside.jpg')])):
            (work/'capture.json').write_text(json.dumps({**job,**change}))
            with patch.object(self.publisher,'publish') as publish:
                self.assertEqual(self.publisher.recover_pending(),[]);publish.assert_not_called()
        self.publisher.source.fetch.assert_not_called()

if __name__=='__main__':unittest.main()
