"""Actual canonical controller/serializer and synthetic offline staging only.

No queue backend, provider, camera network or physical hardware is contacted.
Synthetic camera encoding is checked separately by the canonical recorder suite.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

from test_controller_bridge import Channel,SerializerStation,command,ROOT
from controller_channel import RootlessControllerChannel
from physical_run import PhysicalRun,stage_controller


class ClosedChannel(Channel):
    def __init__(self,inputs):
        super().__init__(inputs);self.cleanup_confirmed=False
    def start(self,cancelled=lambda:False):
        self.cancelled=cancelled
    def close(self):
        super().close();self.cleanup_confirmed=True


class ReplaySpy:
    model='Gemini Robotics'
    def ready(self):return True
    def start(self,controller):
        self.attempt=controller.status()['attempt_id']
        thread=threading.Thread(target=lambda:None);thread.start();return thread


class PhysicalRunTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def make(self,inputs):
        api=SerializerStation();channel=ClosedChannel(inputs);replay=ReplaySpy()
        run=PhysicalRun(ROOT,api,channel,controller_sha256='c'*64,
            recording_path=self.root/'run_ffffffffffffffffffffffffffffffff',replay=replay)
        run.controller.update_monitor_observation(api.get_robot_observation('yam-1'))
        return run,api,channel,replay

    def test_canonical_worker_preserves_start_records_packets_and_never_restarts(self):
        run,api,channel,replay=self.make([command(0,0.),dict(kind='complete',request_id=1)])
        started=time.time()-8
        run.start('Offline lifecycle fixture',60,launch_requested_at=started)
        status=run.wait(5)
        self.assertFalse(status['worker_alive']);self.assertFalse(status['capture_alive'])
        self.assertTrue(status['controller_finished']);self.assertTrue(status['cleanup_confirmed'])
        self.assertFalse(status['outcome_verified']);self.assertEqual(status['launch_requested_at'],started)
        self.assertEqual(len(api.wire),1);self.assertEqual(api.wire[0]['waypoints'][-1]['left_gripper'],0.)
        self.assertEqual(len(api.create_requests),1)
        with self.assertRaisesRegex(RuntimeError,'cannot be restarted'):
            run.start('Offline lifecycle fixture',60,launch_requested_at=time.time())
        self.assertEqual(len(api.create_requests),1)
        path=self.root/'run_ffffffffffffffffffffffffffffffff'/'interactions.jsonl'
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertTrue(any(row['kind']=='packet_completed' for row in rows))
        text=json.dumps(status)
        self.assertNotIn('lease_id',text);self.assertNotIn('capability',text);self.assertNotIn(str(self.root),text)

    def test_stop_revokes_canonical_session_before_channel_close(self):
        run,api,channel,_=self.make([command(0,0.)]);order=[]
        original=api.stop_session
        def stop(*args,**kwargs):order.append('station_stop');return original(*args,**kwargs)
        api.stop_session=stop
        close=channel.close
        def closed():order.append('channel_close');return close()
        channel.close=closed
        channel.on_receive=lambda:run.stop()
        run.start('Offline cancellation',60,launch_requested_at=time.time())
        status=run.wait(5)
        self.assertFalse(api.wire);self.assertFalse(api.trajectory_attempts)
        self.assertFalse(status['controller_finished']);self.assertFalse(status['worker_alive'])
        self.assertLess(order.index('station_stop'),order.index('channel_close'))

    def test_preparation_cancel_and_cleanup_uncertainty_are_not_completion(self):
        run,api,channel,_=self.make([]);entered=threading.Event()
        def prepare(cancelled):
            entered.set()
            while not cancelled():time.sleep(.001)
            raise RuntimeError('Offline preparation cancelled')
        channel.start=prepare
        run.start('Offline preparation cancellation',60,launch_requested_at=time.time())
        self.assertTrue(entered.wait(1));run.stop();status=run.wait(5)
        self.assertFalse(api.create_requests);self.assertFalse(status['controller_finished'])
        run,api,channel,_=self.make([dict(kind='complete',request_id=0)])
        channel.close=Mock(side_effect=RuntimeError('Synthetic unknown cleanup'))
        run.start('Offline cleanup uncertainty',60,launch_requested_at=time.time())
        with self.assertRaisesRegex(RuntimeError,'unknown cleanup'):run.wait(5)
        self.assertTrue(run.status()['cleanup_error']);self.assertFalse(run.status()['cleanup_confirmed'])
        with self.assertRaises(RuntimeError):run.start('No replay',60,launch_requested_at=time.time())
        self.assertEqual(len(api.create_requests),1)

    def test_unavailable_recorder_submits_no_queue_or_generated_process(self):
        run,api,channel,replay=self.make([]);replay.ready=lambda:False;channel.start=Mock()
        with self.assertRaisesRegex(RuntimeError,'encoder is unavailable'):
            run.start('Offline missing encoder',60,launch_requested_at=time.time())
        self.assertFalse(api.create_requests);channel.start.assert_not_called()

    def test_capture_start_failure_stops_the_created_session_without_motion(self):
        run,api,channel,replay=self.make([]);created=threading.Event()
        original=api.create_session
        def create(*args,**kwargs):
            result=original(*args,**kwargs);created.set();return result
        api.create_session=create
        def receive(cancelled):
            while not cancelled():time.sleep(.001)
            return json.dumps(dict(kind='complete',request_id=0))
        channel.receive=receive
        def fail(controller):
            self.assertTrue(created.wait(1));raise RuntimeError('Synthetic capture startup failure')
        replay.start=fail
        with self.assertRaisesRegex(RuntimeError,'capture startup failure'):
            run.start('Offline capture failure',60,launch_requested_at=time.time())
        status=run.wait(5)
        self.assertEqual(len(api.create_requests),1);self.assertTrue(status['cleanup_confirmed'])
        self.assertFalse(status['worker_alive']);self.assertFalse(api.wire)
        self.assertTrue(run.controller.status()['return_to_rest_requested'])
        with self.assertRaises(RuntimeError):run.start('No restart',60,launch_requested_at=time.time())

    def test_staging_uses_retained_bound_source_and_rejects_changed_inputs(self):
        source=self.root/'evidence';source.mkdir()
        data={'controller.py':b'def run(env): pass\n','station.json':json.dumps({'calibration':json.loads((Path(__file__).parent/'fixtures/yam1-calibration.json').read_text())}).encode()}
        for name,value in data.items():(source/name).write_bytes(value)
        receipt=dict(id='a'*32,variant='yam1',image='sha256:'+'b'*64,exit_code=0,
            binding_passed=True,cleanup_confirmed=True,controller_sha256=hashlib.sha256(data['controller.py']).hexdigest(),
            station_snapshot_sha256=hashlib.sha256(data['station.json']).hexdigest())
        result=stage_controller(source,receipt,self.root/'job',ROOT,image=receipt['image'])
        self.assertEqual((self.root/'job/controller.py').read_bytes(),data['controller.py'])
        self.assertEqual(result['controller_sha256'],receipt['controller_sha256'])
        self.assertTrue((self.root/'job/controller-runtime/config.json').is_file())
        (source/'controller.py').write_text('changed')
        with self.assertRaisesRegex(ValueError,'input changed'):
            stage_controller(source,receipt,self.root/'bad',ROOT,image=receipt['image'])
        self.assertFalse((self.root/'bad').exists())
        for changes in ({'binding_passed':False},{'cleanup_confirmed':False},{'image':'different'}):
            with self.assertRaises(ValueError):stage_controller(source,{**receipt,**changes},self.root/'bad',ROOT,image=receipt['image'])

    def test_bound_rootless_source_changed_or_closed_is_zero_process_and_queue(self):
        (self.root/'controller.py').write_bytes(b'original')
        channel=RootlessControllerChannel(self.root,deadline_monotonic=time.monotonic()+5)
        channel.bind_controller(hashlib.sha256(b'original').hexdigest())
        (self.root/'controller.py').write_bytes(b'changed')
        with patch.object(channel.executor,'command') as command,patch('controller_channel.subprocess.Popen') as process:
            with self.assertRaisesRegex(RuntimeError,'changed before launch'):channel.start()
            command.assert_not_called();process.assert_not_called()
            channel.close();self.assertTrue(channel.cleanup_confirmed)
            with self.assertRaisesRegex(RuntimeError,'cannot be restarted'):channel.start()
            process.assert_not_called()


if __name__=='__main__':unittest.main()
