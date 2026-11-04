"""Regression for the installed canonical publisher without a limit keyword."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('capture_upload',Path(__file__).parents[1]/'scene_capture_upload.py')
upload=importlib.util.module_from_spec(spec);spec.loader.exec_module(upload)

class PublisherTests(unittest.TestCase):
    def test_deployed_signature_and_exact_source_result(self):
        calls=[]
        def installed(root,api=None,*,repo='andlyu/Public-YAM-runs'):
            calls.append(root);return [dict(episode_id='ep_other',status='uploaded'),dict(episode_id='ep_capture',status='uploaded',lerobot_episode_index=603)]
        # Reproduce the actual rejected old invocation before testing the bridge.
        with self.assertRaisesRegex(TypeError,'limit'):installed(Path('/saved'),limit=1)
        result=upload.publish_selected(installed,Path('/saved'),'ep_capture')
        self.assertEqual(result['lerobot_episode_index'],603);self.assertEqual(calls,[Path('/saved')])
    def test_incomplete_or_wrong_recording_never_claims_publication(self):
        for records in ([],[dict(episode_id='ep_other',status='uploaded')],[dict(episode_id='ep_capture',status='retrying')]):
            with self.assertRaisesRegex(RuntimeError,'did not complete'):
                upload.publish_selected(lambda root:records,Path('/saved'),'ep_capture')
    def test_task_and_cutoff_are_required(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'ep_capture';p.mkdir();m=dict(episode_id='ep_capture',task=upload.TASK,status='finalized',simulated=False,started_at=20,samples_sha256='a'*64)
            for change,expected in (({},True),({'task':'different'},False),({'started_at':9},False),({'status':'recording'},False),({'simulated':True},False)):
                (p/'manifest.json').write_text(json.dumps({**m,**change}));self.assertEqual(upload.eligible(p,10),expected)

class CloudHandoffTests(unittest.TestCase):
    def run_one(self,probe):
        import tempfile,json,types,io
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            episode=Path(temp)/'ep_capture';episode.mkdir()
            manifest=dict(episode_id='ep_capture',task=upload.TASK,status='finalized',simulated=False,started_at=20,samples_sha256='a'*64)
            for filename in upload.FILES:(episode/filename).write_text(json.dumps(manifest) if filename=='manifest.json' else 'saved')
            args=types.SimpleNamespace(episode=episode,since=10,ssh='ssh',host='existing-host',cloud_root='/saved',cloud_script='/code/scene_capture_upload.py')
            calls=[]
            def run(command,**kwargs):
                calls.append(command);return types.SimpleNamespace(stdout=json.dumps(probe),returncode=0)
            with patch.object(upload.subprocess,'run',side_effect=run),patch.object(upload,'urlopen',return_value=io.BytesIO(b'{"episode_id":"ep_capture"}')):
                upload.one(args)
            return calls,json.loads((episode/'scene-upload.json').read_text())
    def test_transfer_hands_off_to_bounded_independent_cloud_job(self):
        calls,state=self.run_one(dict(status='pending',active=False))
        self.assertEqual(state['status'],'publishing')
        self.assertTrue(any(c[0]=='rsync' for c in calls))
        commands=' '.join(str(c) for c in calls)
        for argument in ('systemd-run','RuntimeMaxSec=900','MemoryMax=768M','CPUQuota=80%','--uid=ubuntu'):
            self.assertIn(argument,commands)
        self.assertFalse(any(k in commands for k in ('submit_trajectory','create_session','camera_owner')))
    def test_active_cloud_job_is_observed_without_retransferring_or_restarting(self):
        calls,state=self.run_one(dict(status='pending',active=True))
        self.assertEqual(len(calls),1);self.assertEqual(state['status'],'publishing')
    def test_completed_receipt_is_recovered_without_republication(self):
        calls,state=self.run_one(dict(status='uploaded',samples_sha256='a'*64,episode_index=603))
        self.assertEqual(len(calls),1);self.assertEqual(state['episode_index'],603)

class EncoderResourceTests(unittest.TestCase):
    def test_filter_thread_limits_preserve_native_encoder_arguments(self):
        spec=importlib.util.spec_from_file_location('capture_ffmpeg',Path(__file__).parents[1]/'scene_capture_ffmpeg.py')
        ffmpeg=importlib.util.module_from_spec(spec);spec.loader.exec_module(ffmpeg)
        arguments=['-f','rawvideo','-video_size','640x360','-framerate','10','-i','-','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','episode.mp4']
        command=ffmpeg.encoder_command(arguments)
        self.assertEqual(command[:5],['/usr/bin/ffmpeg','-filter_threads','1','-filter_complex_threads','1'])
        self.assertEqual(command[5:],arguments)
