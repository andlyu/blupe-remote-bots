"""Worker/Store -> quiet serializer -> real controller -> synthetic recorder.

No live endpoint, human contact, camera, paid model or motor is used. A mock
station emits canonical events/feedback; real ffmpeg encodes synthetic JPEGs.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch,AsyncMock
import uuid

from test_worker import w,request
from test_controller_bridge import SerializerStation,command,ROOT
from test_physical_run import ClosedChannel
from test_quiet_session import contract
from test_simulation_binding import EditingAgent,ScriptedExecutor
from physical_run import PhysicalRun
from physical_store import run_physical
from physical_evidence import retain_physical,public_status,public_native_event
from quiet_session import GeminiSessionAPI,QUIET_PATH
from remote_yam import session
from remote_yam.cameras import CameraFrame
from remote_yam.roboharness_replay import PublicCameraReplay
from PIL import Image


class QuietStation(SerializerStation):
    def __init__(self,name,email):
        super().__init__();self.name=name;self.email=email;self.queue_wire=[]
        self.quiet=GeminiSessionAPI(name,email,websocket_factory=object())
    def create_session(self,prompt,run_duration_s=300,**kwargs):
        def transport(req,**options):
            if req.method=='GET':return io.BytesIO(json.dumps(contract()).encode())
            if not req.full_url.endswith(QUIET_PATH):raise AssertionError('Ordinary email endpoint is forbidden')
            payload=json.loads(req.data);self.queue_wire.append(payload)
            if payload['email_queue_alert'] is not False or payload['email_run_video'] is not False:
                raise AssertionError('Both notification paths must be disabled')
            created=super(QuietStation,self).create_session(prompt,run_duration_s,runner_name=payload['runner_name'],
                email=payload['email'],model=payload['model'])
            return io.BytesIO(json.dumps({**created,'session_capability':'synthetic-only-capability'}).encode())
        with patch.object(session.request,'urlopen',transport):return self.quiet.create_session(prompt,run_duration_s,**kwargs)


class PhysicalStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=w.Store(self.root)
        self.spec=w.RunInput(request_id=uuid.uuid4(),runner_name='Test researcher',email='private@example.test',
            prompt='Offline Store pipeline fixture',mode='robot',duration_s=60,launch_requested_at=time.time()-5)
        self.job=self.store.create(self.spec,'a'*64)
        self.receipt=self.evidence()
        image=io.BytesIO();Image.new('RGB',(64,48),'red').save(image,format='JPEG');self.jpeg=image.getvalue()
        self.apis=[];self.runs=[];self.first_packet=threading.Event()
        self.env=patch.dict(os.environ,{'GEMINI_SIM_IMAGE':'sha256:'+'c'*64,'GEMINI_RUNNER_ROOT':str(ROOT)})
        self.env.start();self.addCleanup(self.env.stop)

    def evidence(self):
        code=b'def run(env): pass\n'
        station=json.dumps({'calibration':json.loads((Path(__file__).parent/'fixtures/yam1-calibration.json').read_text())}).encode()
        execution=uuid.uuid4().hex;folder=self.root/'simulation-evidence'/self.job['id']/execution;folder.mkdir(parents=True)
        (folder/'controller.py').write_bytes(code);(folder/'station.json').write_bytes(station)
        return dict(id=execution,binding_passed=True,cleanup_confirmed=True,variant='yam1',image='sha256:'+'c'*64,
            exit_code=0,controller_sha256=hashlib.sha256(code).hexdigest(),station_snapshot_sha256=hashlib.sha256(station).hexdigest())

    def api(self,name,email):
        result=QuietStation(name,email);self.apis.append(result);return result

    def channel(self,workspace,**kwargs):
        channel=ClosedChannel([command(0,0.),dict(kind='complete',request_id=1)])
        original=channel.receive
        def receive(cancelled):
            if channel.inputs and channel.inputs[0]['kind']=='complete':
                self.first_packet.set()
                deadline=time.monotonic()+.7
                while not cancelled() and time.monotonic()<deadline:time.sleep(.005)
            return original(cancelled)
        channel.receive=receive;return channel

    def run_host(self,*args,**kwargs):
        replay=PublicCameraReplay(self.root/'native-replays',robot_id='yam-1',model='Gemini Robotics')
        replay.source.fetch=Mock(side_effect=lambda *a:CameraFrame('top',self.jpeg,time.time(),source_captured_at=time.time()-.01))
        result=PhysicalRun(*args,**kwargs,replay=replay)
        result.controller.update_monitor_observation(args[1].get_robot_observation('yam-1'))
        self.runs.append(result);return result

    def cameras(self):
        frame=lambda name:CameraFrame(name,self.jpeg,time.time(),source_captured_at=time.time()-.01)
        class Cameras:
            def __init__(self,*args):pass
            def capture_for_policy(self,*args,**kwargs):return [frame(n) for n in ('top','left','right')]
        return (None,Cameras)

    async def execute(self):
        with patch('physical_store.transport_classes',side_effect=self.cameras),patch.object(session.request,'urlopen',side_effect=AssertionError('No live network')):
            await run_physical(self.store,self.job['id'],self.receipt,api_factory=self.api,
                channel_factory=self.channel,run_factory=self.run_host,poll_s=.01)

    def test_real_pipeline_retains_quiet_identity_original_start_and_authenticated_video_range(self):
        asyncio.run(self.execute());job=self.store.get(self.job['id'])
        self.assertEqual(job['state'],'complete',job['progress'])
        api=self.apis[0];self.assertEqual(len(api.queue_wire),1);self.assertEqual(len(api.wire),1)
        self.assertEqual(api.queue_wire[0]['runner_name'],self.spec.runner_name)
        self.assertEqual(api.queue_wire[0]['email'],self.spec.email);self.assertEqual(api.queue_wire[0]['model'],'Gemini Robotics')
        self.assertFalse(api.queue_wire[0]['email_queue_alert']);self.assertFalse(api.queue_wire[0]['email_run_video'])
        self.assertEqual(job['launch_requested_at'],self.spec.launch_requested_at)
        self.assertNotIn(self.spec.email,json.dumps(job))
        video=next(a for a in job['artifacts'] if a['name']=='physical.mp4')
        self.assertEqual(video['kind'],'physical')
        report=json.loads((self.root/'physical-evidence'/job['id']/'physical.json').read_text())
        self.assertEqual(report['timing']['t_run'],self.spec.launch_requested_at)
        self.assertEqual(report['timing']['home_target'],'unverified');self.assertIsNone(report['timing']['t_motion'])
        self.assertFalse(report['outcome_verified']);self.assertNotIn(self.spec.email,json.dumps(report))
        app=w.create_app(self.root)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'synthetic-site'}):
            status,_=asyncio.run(request(app,video['url']));self.assertEqual(status,403)
            status,data=asyncio.run(request(app,video['url'],headers={'x-gemini-site-token':'synthetic-site','range':'bytes=0-63'},as_json=False))
            self.assertEqual(status,206);self.assertEqual(len(data),64);self.assertIn(b'ftyp',data)
            (self.root/'physical-evidence'/job['id']/'physical.mp4').write_bytes(b'changed host artifact')
            status,_=asyncio.run(request(app,video['url'],headers={'x-gemini-site-token':'synthetic-site'}));self.assertEqual(status,404)

    def test_native_rejection_corrected_dispatch_and_measured_completion_reach_store_once(self):
        original=self.channel
        def corrected(*args,**kwargs):
            channel=original(*args,**kwargs)
            channel.inputs[:]=[command(0,-1e-16),command(1,0.),dict(kind='complete',request_id=2)]
            return channel
        self.channel=corrected
        asyncio.run(self.execute());job=self.store.get(self.job['id'])
        self.assertEqual(job['state'],'complete',job['progress'])
        messages=[row['message'] for row in job['events']]
        expected=('Local command rejected before dispatch','Method packet passed local validation',
                  'Sending the validated packet','Packet accepted for dispatch',
                  'Gateway validated the packet','Measured feedback completed')
        positions=[]
        for text in expected:
            matches=[i for i,value in enumerate(messages) if value.startswith(text)]
            self.assertEqual(len(matches),1,(text,messages));positions.append(matches[0])
        self.assertEqual(positions,sorted(positions))
        self.assertEqual(len(self.apis[0].wire),1)
        native=self.runs[0].native_events()[1]
        rejected=next(row for row in native if row['kind']=='controller_rejected')
        public=next(row for row in job['events'] if row['message'].startswith(expected[0]))
        self.assertEqual(public['at'],rejected['timestamp'])

    def test_native_event_projection_never_exposes_native_text_details_or_nonfinite_clock(self):
        secret='private@example.test capability_xyz /private/path synthetic-model-key'
        row=dict(kind='controller_rejected',timestamp=123.5,message=secret,details={'lease':secret})
        projected=public_native_event(row)
        self.assertEqual(set(projected),{'stage','message','at'})
        self.assertNotIn(secret,json.dumps(projected));self.assertEqual(projected['at'],123.5)
        self.assertIsNone(public_native_event({**row,'kind':'private_runtime_config'}))
        self.assertIsNone(public_native_event({**row,'timestamp':float('nan')}))
        self.assertIsNone(public_native_event({**row,'timestamp':True}))

    def test_http_stop_remains_pending_until_real_controller_and_recorder_close(self):
        async def scenario():
            task=asyncio.create_task(self.execute())
            self.assertTrue(await asyncio.to_thread(self.first_packet.wait,3))
            app=w.create_app(self.root)
            with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'synthetic-site'}):
                code,_=await request(app,f'/api/runs/{self.job["id"]}/stop','POST',{},
                    {'x-gemini-site-token':'synthetic-site','x-gemini-visitor':'a'*64})
            self.assertEqual(code,200);self.assertEqual(self.store.get(self.job['id'])['state'],'stopping')
            self.store.event(self.job['id'],'complete','A late completion must not win')
            self.assertEqual(self.store.get(self.job['id'])['state'],'stopping')
            await task
        asyncio.run(scenario());job=self.store.get(self.job['id'])
        self.assertEqual(job['state'],'cancelled',job['progress']);self.assertIn('Stop acknowledged',job['progress'])
        self.assertFalse(job['configuration']['physical']['worker_alive'])
        self.assertTrue(job['configuration']['physical']['cleanup_confirmed'])
        self.assertEqual(len(self.apis[0].queue_wire),1);self.assertEqual(len(self.apis[0].wire),1)

    def test_cleanup_failure_still_retains_finished_camera_footage_without_claiming_completion(self):
        original=self.run_host
        def failing(*args,**kwargs):
            run=original(*args,**kwargs)
            run.channel.close=Mock(side_effect=RuntimeError('Synthetic cleanup uncertainty'))
            return run
        self.run_host=failing
        asyncio.run(self.execute());job=self.store.get(self.job['id'])
        self.assertEqual(job['state'],'failed')
        self.assertIn('unverified',job['progress'])
        self.assertTrue(any(a['name']=='physical.mp4' for a in job['artifacts']))
        self.assertFalse(job['configuration']['physical']['cleanup_confirmed'])
        self.assertFalse(job['configuration']['physical']['capture_alive'])
        self.assertEqual(len(self.apis[0].queue_wire),1)

    def test_simulation_mode_cannot_reach_any_physical_factory(self):
        spec=self.spec.model_copy(update={'request_id':uuid.uuid4(),'mode':'simulation'})
        job=self.store.create(spec,'a'*64);api=Mock();channel=Mock();stage=Mock()
        with self.assertRaisesRegex(ValueError,'Simulation requests'):
            asyncio.run(run_physical(self.store,job['id'],self.receipt,api_factory=api,channel_factory=channel,stage=stage))
        api.assert_not_called();channel.assert_not_called();stage.assert_not_called()

    def test_stop_before_handoff_is_zero_identity_queue_or_process(self):
        self.store.request_stop(self.job['id'])
        api=Mock();channel=Mock()
        asyncio.run(run_physical(self.store,self.job['id'],self.receipt,api_factory=api,channel_factory=channel))
        api.assert_not_called();channel.assert_not_called()
        self.assertEqual(self.store.get(self.job['id'])['state'],'cancelled')

    def test_stop_and_late_progress_are_atomic_and_typed_projection_excludes_private_fields(self):
        self.store.event(self.job['id'],'running','Offline running fixture')
        barrier=threading.Barrier(2)
        def stop():barrier.wait();self.store.request_stop(self.job['id'])
        def progress():barrier.wait();self.store.event(self.job['id'],'running','Late running')
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(stop);b=pool.submit(progress);a.result();b.result()
        self.assertEqual(self.store.get(self.job['id'])['state'],'stopping')
        self.store.physical_status(self.job['id'],dict(status=self.spec.email,episode_id=self.spec.email,
            lease_id=self.spec.email,worker_alive=self.spec.email,cleanup_confirmed=True,outcome_verified=True))
        projection=self.store.get(self.job['id'])['configuration']['physical']
        self.assertNotIn(self.spec.email,json.dumps(projection));self.assertIsNone(projection['worker_alive'])
        self.assertFalse(projection['outcome_verified']);self.assertEqual(projection['status'],'unknown')

    def test_missing_or_wrong_capture_is_a_retained_gap_not_fake_physical_video(self):
        status=dict(episode_id='ep_offline',status='stopped',cleanup_confirmed=True)
        binding=dict(controller_sha256='c'*64,simulation_execution_id=self.receipt['id'])
        replay=self.root/'bad-replay';replay.mkdir()
        meta=dict(episode_id='ep_offline',robot_id='yam-1',model='Wrong method',email=self.spec.email,
            preview={'sha256':'a'*64,'duration_s':1,'speed':1,'camera_order':['top']})
        (replay/'ep_offline.json').write_text(json.dumps(meta))
        result,artifacts=retain_physical(self.root,self.job,binding,status,replay)
        self.assertEqual(result['capture_status'],'unavailable');self.assertFalse(result['outcome_verified'])
        self.assertEqual([a['name'] for a in artifacts],['physical.json'])
        self.assertNotIn(self.spec.email,json.dumps(result));self.assertFalse((self.root/'physical-evidence'/self.job['id']/'physical.mp4').exists())

    def test_scripted_sdk_handoff_calls_physical_composition_only_for_matching_source(self):
        for edit_after,called in ((False,True),(True,False)):
            with self.subTest(edit_after=edit_after):
                spec=self.spec.model_copy(update={'request_id':uuid.uuid4()});job=self.store.create(spec,'a'*64)
                EditingAgent.edit_after=edit_after;EditingAgent.resimulate=False;EditingAgent.identical_write=False
                ScriptedExecutor.tamper_station_once=False
                station={'calibration':{'calibration_id':'offline'},'observation':{'source':'offline'},'camera_frames':[]}
                physical=AsyncMock()
                with patch.dict(os.environ,{'GEMINI_API_KEY':'synthetic-key'}),patch.object(w,'SimulationExecutor',ScriptedExecutor),\
                    patch('google.antigravity.Agent',EditingAgent),patch('station_inputs.collect_station_inputs',return_value=(station,[])),\
                    patch('station_inputs.sdk_prompt',return_value=['offline']),patch('physical_store.run_physical',physical):
                    asyncio.run(w.run_agent(self.store,job['id'],self.root))
                self.assertEqual(physical.await_count,int(called))
                self.assertNotEqual(self.store.get(job['id'])['state'],'complete')

    def test_store_transactions_close_connections_and_keep_durable_state(self):
        import sqlite3
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        self.store.event(self.job['id'],'running','Durable offline fixture')
        self.assertEqual(w.Store(self.root).get(self.job['id'])['state'],'running')

    def test_start_timestamp_idempotence_and_old_rows_remain_readable(self):
        same=self.store.create(self.spec,'a'*64);self.assertEqual(same['launch_requested_at'],self.spec.launch_requested_at)
        with self.assertRaises(w.HTTPException):self.store.create(self.spec.model_copy(update={'launch_requested_at':time.time()}),'a'*64)
        with self.assertRaises(w.HTTPException):self.store.create(self.spec.model_copy(update={'request_id':uuid.uuid4(),'launch_requested_at':float('nan')}),'a'*64)
        row=self.store.get(self.job['id']);row.pop('launch_requested_at');row.pop('stop_requested_at')
        with self.store.connect() as db:db.execute('UPDATE runs SET data=? WHERE id=?',(json.dumps(row),self.job['id']))
        app=w.create_app(self.root)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'synthetic-site'}):
            code,data=asyncio.run(request(app,'/api/state',headers={'x-gemini-site-token':'synthetic-site'}))
        self.assertEqual(code,200);self.assertIsNone(data['runs'][0]['launch_requested_at'])
        self.assertNotIn(self.spec.email,json.dumps(data))


if __name__=='__main__':unittest.main()
