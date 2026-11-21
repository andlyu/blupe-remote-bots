"""Real encoder and immutable Kinex-attributed upload; zero camera/robot traffic."""
import io,json,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'integrations/kinex'))
from replay import KinexReplay,ClockedCamera,CameraSample
from remote_yam.cameras import CameraFrameSource
from remote_yam.kinex_safety import ROBOHOUSE

class RetainedReplay(unittest.TestCase):
    def test_real_encoding_upload_has_kinex_episode_and_exact_digest(self):
        import hashlib,subprocess
        seen=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'work';work.mkdir();frames=[];start=time.time()-2
            for i,color in enumerate(('red','green','blue')):
                name=f'{i:06d}.jpg';Image.new('RGB',(64,64),color).save(work/name)
                frames.append(dict(file=name,received_at=start+i*.5,source_captured_at=start+i*.5-.02,actual_image=True))
            state=dict(attempt_id='attempt',episode_id='ep_offline_kinex',session_id='session')
            replay=KinexReplay(root,robot_id=ROBOHOUSE,upload=lambda meta,path:seen.append((meta,path.read_bytes())) or {'ok':True})
            replay.controller=SimpleNamespace(status=lambda:state);replay.attempt='attempt';replay.allow_publish()
            meta=replay.publish(work,'ep_offline_kinex',frames,partial=False,started_at=start-.1,ended_at=start+1.5)
            self.assertEqual(meta['model'],'Kinex');self.assertEqual(meta['session_id'],'session');self.assertEqual(meta['capture_fps'],2)
            self.assertEqual(seen[0][0]['episode_id'],'ep_offline_kinex');self.assertEqual(hashlib.sha256(seen[0][1]).hexdigest(),meta['preview']['sha256'])
            stored=json.loads((root/'ep_offline_kinex.json').read_text());self.assertEqual(stored['model'],'Kinex');self.assertEqual(replay.result,{'ok':True})
            path=root/'ep_offline_kinex'/(meta['preview']['sha256']+'.mp4')
            probe=subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name','-of','json',str(path)],text=True)
            self.assertEqual(json.loads(probe)['streams'][0]['codec_name'],'h264')
            replay.attempt='other'
            with self.assertRaisesRegex(RuntimeError,'attempt'):replay.publish(work,'ep_offline_kinex',frames,partial=False,started_at=start,ended_at=start+1.5)
            self.assertEqual(len(seen),1)

    def test_camera_small_clock_lead_waits_without_fabricating_frame_or_widening_freshness(self):
        frame=CameraSample('top',b'jpeg',100,source_captured_at=100.1)
        source=ClockedCamera('https://example.test',camera_names=('top',))
        with patch.object(CameraFrameSource,'fetch',return_value=frame),patch('replay.time.time',return_value=100),patch('replay.time.sleep') as wait:
            self.assertIs(source.fetch('top','https://example.test/top.jpg'),frame);self.assertAlmostEqual(wait.call_args.args[0],.102)
        far=CameraSample('top',b'jpeg',100,source_captured_at=101)
        with patch.object(CameraFrameSource,'fetch',return_value=far),patch('replay.time.time',return_value=100),patch('replay.time.sleep') as wait:
            self.assertIs(source.fetch('top','https://example.test/top.jpg'),far);wait.assert_not_called()  # Shared recorder rejects it.

    def test_source_reply_after_terminal_is_discarded_and_never_uploaded(self):
        image=io.BytesIO();Image.new('RGB',(64,64),'red').save(image,format='JPEG')
        state=dict(status='running',attempt_id='attempt',episode_id='ep_boundary',session_id='session',run_started_at=100)
        events=[];uploads=[]
        controller=SimpleNamespace(status=lambda:dict(state),_interactions=SimpleNamespace(add=lambda kind,message,**details:events.append(kind)))
        with tempfile.TemporaryDirectory() as directory:
            r=KinexReplay(directory,robot_id=ROBOHOUSE,upload=lambda *args:uploads.append(args));r.controller=controller;r.attempt='attempt';r.allow_publish()
            def fetch(*args):
                state['status']='stopped'
                return CameraSample('top',image.getvalue(),100,99.99)
            r.source=SimpleNamespace(fetch=fetch)
            r.follow(controller,'attempt',clock=lambda:100,sleep=lambda _:None)
            self.assertEqual(uploads,[]);self.assertIn('replay_failed',events)
            self.assertFalse(list(Path(directory).rglob('*.mp4')))

    def test_encoder_waits_for_terminal_publication_and_honors_cancel(self):
        import threading
        from camera_replay import PublicCameraReplay
        waiting=threading.Event()
        class ObservedEvent(threading.Event):
            def wait(self,timeout=None):waiting.set();return super().wait(timeout)
        for cancel in (False,True):
            with self.subTest(cancel=cancel),tempfile.TemporaryDirectory() as directory:
                r=KinexReplay(directory,robot_id=ROBOHOUSE,upload=lambda *args:self.fail('Unexpected upload'))
                r.controller=SimpleNamespace(status=lambda:dict(attempt_id='a',episode_id='ep_a',session_id='session'));r.attempt='a';r._publication_allowed=ObservedEvent();errors=[];waiting.clear()
                def publish():
                    try:r.publish(Path(directory),'ep_a',[],partial=False,started_at=100,ended_at=101)
                    except RuntimeError as e:errors.append(str(e))
                with patch.object(PublicCameraReplay,'publish',side_effect=RuntimeError('encoder reached')) as encoder:
                    thread=threading.Thread(target=publish);thread.start();self.assertTrue(waiting.wait(1));encoder.assert_not_called()
                    if cancel:r.close()
                    else:r.allow_publish()
                    thread.join(2);self.assertFalse(thread.is_alive())
                    self.assertEqual(encoder.call_count,0 if cancel else 1)
                    self.assertTrue(errors)

    def test_previous_episode_video_counts_against_shared_disk_budget(self):
        events=[];uploads=[]
        c=SimpleNamespace(status=lambda:dict(status='running',attempt_id='a',episode_id='ep_new'),_interactions=SimpleNamespace(add=lambda kind,message,**kw:events.append(kind)))
        with tempfile.TemporaryDirectory() as directory:
            previous=Path(directory)/'ep_previous';previous.mkdir()
            with (previous/'large.mp4').open('wb') as f:f.truncate(1024*1024*1024+1)
            r=KinexReplay(directory,robot_id=ROBOHOUSE,upload=lambda *args:uploads.append(args));r.source=SimpleNamespace(fetch=lambda *args:self.fail('Budget must reject before capture'))
            r.follow(c,'a');self.assertIn('replay_failed',events);self.assertEqual(uploads,[])

    def test_jpeg_reader_requires_headers_complete_body_timestamp_and_trusted_origin(self):
        from email.message import Message
        image=io.BytesIO();Image.new('RGB',(64,64),'blue').save(image,format='JPEG');jpeg=image.getvalue()
        source=ClockedCamera('https://example.test',camera_names=('top',))
        def response(payload=jpeg,**headers):
            r=io.BytesIO(payload);r.headers=Message()
            for k,v in {'Content-Type':'image/jpeg','Content-Length':str(len(jpeg)),'X-Captured-At':'100',**headers}.items():r.headers[k]=v
            return r
        with patch('replay.build_opener') as opener,patch('replay.time.time',return_value=100.1):
            opener.return_value.open.return_value=response();self.assertEqual(source.fetch('top','https://example.test/top.jpg').jpeg,jpeg)
            for bad in [response(**{'Content-Type':'image/png'}),response(**{'Content-Length':str(3*1024*1024)}),response(**{'X-Captured-At':'nan'}),response(payload=jpeg[:-2])]:
                opener.return_value.open.return_value=bad
                with self.assertRaises(ValueError):source.fetch('top','https://example.test/top.jpg')
            opener.reset_mock()
            with self.assertRaises(ValueError):source.fetch('top','https://other.test/top.jpg')
            opener.assert_not_called()
