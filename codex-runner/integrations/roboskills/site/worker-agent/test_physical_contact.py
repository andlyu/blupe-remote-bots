import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from physical_worker import PhysicalWorker


class FakeClient:
    instance = None
    start_failure = None
    responses = []

    def __init__(self, *args, **kwargs):
        type(self).instance = self
        self.starts = self.stops = self.reads = 0
        self.attempt_id = None
        self.values = iter(type(self).responses)

    def connect(self): pass
    def start(self, *args, **kwargs):
        self.starts += 1
        if self.start_failure: raise self.start_failure
        self.attempt_id = 'owned-attempt'
    def save(self, path): Path(path).write_text('test-only-handle')
    def stop(self): self.stops += 1
    def status(self):
        self.reads += 1
        value = next(self.values)
        if isinstance(value, Exception): raise value
        return value


DONE = {'status':'stopped', 'packets_submitted':2, 'provider':{'outcome':{
    'status':'done', 'task_status':'reported_failure', 'reason':'No stack'}}}


class FakeWorker(PhysicalWorker):
    def __init__(self, root):
        self.root = Path(root)
        self.config = {'harness':'http://127.0.0.1:8797'}
        self.requests = []
        self.heartbeat_failures = []
    def record(self, stop, folder): pass
    def request(self, action, body=None, **kwargs):
        self.requests.append((action, body))
        if action == 'heartbeat' and self.heartbeat_failures:
            raise self.heartbeat_failures.pop(0)
        return {}


class ContactTests(unittest.TestCase):
    def run_worker(self, responses, *, heartbeat_failures=(), start_failure=None):
        FakeClient.responses = responses
        FakeClient.start_failure = start_failure
        with tempfile.TemporaryDirectory() as root:
            w = FakeWorker(root)
            w.heartbeat_failures = list(heartbeat_failures)
            with patch('physical_worker.RunnerPolicyClient', FakeClient), patch('physical_worker.time.sleep'):
                w.execute({'id':'test-run', 'runnerName':'Test runner', 'runnerEmail':'test@example.com', 'instruction':'Test fixture, no robot'})
            final = [b for a,b in w.requests if a=='update'][-1]
            return w, FakeClient.instance, final

    def test_status_reset_reconciles_same_run_without_start_or_motion_retry(self):
        w,c,final = self.run_worker([ConnectionResetError(54,'Connection reset by peer'), DONE])
        self.assertEqual(final['status'],'finished')
        self.assertEqual((c.starts,c.reads,c.stops),(1,2,0))
        self.assertTrue(any('Reconnecting' in b.get('stage','') for a,b in w.requests if a=='update'))
        self.assertEqual(final['result']['packets_submitted'],2)

    def test_idempotent_heartbeat_reset_reconnects_and_keeps_same_attempt(self):
        w,c,final = self.run_worker([DONE], heartbeat_failures=[ConnectionResetError(54,'reset')])
        self.assertEqual(final['status'],'finished')
        self.assertEqual((c.starts,c.reads,c.stops),(1,1,0))
        self.assertEqual(sum(a=='heartbeat' for a,b in w.requests),2)

    def test_read_retries_are_bounded_and_owned_stop_is_once(self):
        w,c,final = self.run_worker([ConnectionResetError(54,'reset') for _ in range(3)])
        self.assertEqual(final['status'],'failed')
        self.assertEqual((c.starts,c.reads,c.stops),(1,3,1))

    def test_auth_denial_is_not_retried(self):
        w,c,final = self.run_worker([HTTPError('http://127.0.0.1:8797/api/status',403,'Forbidden',{},None)])
        self.assertEqual(final['status'],'failed')
        self.assertEqual((c.starts,c.reads,c.stops),(1,1,1))

    def test_uncertain_start_is_never_replayed(self):
        w,c,final = self.run_worker([],start_failure=ConnectionResetError(54,'reset'))
        self.assertEqual(final['status'],'failed')
        self.assertEqual((c.starts,c.reads),(1,0))
