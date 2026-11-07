import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from remote_yam.past_runs import RunNames,public_runner_diagnostic
from remote_yam.run_errors import public_run_error
from remote_yam.remote_session_policy import RemoteSessionPolicy

class WorkspaceStopDiagnosticTests(unittest.TestCase):
    def test_exact_native_and_fixed_messages_survive_both_filters(self):
        for side in ('left','right'):
            fixed=f'Robot safety stop: {side} tip left the configured workspace'
            for prefix in ('','RuntimeError: ','ValueError: '):
                for source in (f'{side}_tip_outside_workspace at waypoint 0',
                               f'{side}_tip_outside_workspace at waypoint 9999',fixed):
                    self.assertEqual(public_runner_diagnostic({'error':prefix+source}),fixed)
                    self.assertEqual(public_run_error({'error':prefix+source}),fixed)

    def test_unrelated_errors_and_arbitrary_tails_are_rejected(self):
        for source in ('right_tip_outside_workspace at waypoint 10000',
            'right_tip_outside_workspace at waypoint -1',
            'right_tip_outside_workspace at waypoint 0 private details',
            'right_tip_outside_workspace at waypoint 0\nsecret',
            'left_tip_outside_workspace at waypoint 1.0',
            'Robot safety stop: right tip left the configured workspace https://private.invalid',
            'middle_tip_outside_workspace at waypoint 0'):
            self.assertIsNone(public_runner_diagnostic({'error':source}))

    def test_hosted_adapter_still_stops_without_replaying_execution(self):
        calls=[]
        p=RemoteSessionPolicy('http://127.0.0.1:8798','fixture'*8,
            provider_name='private',display_name='Private policy',model='right',robot_id='yam-1')
        def request(path,payload=None):
            calls.append(path);return dict(status='failed',error='right_tip_outside_workspace at waypoint 0')
        p._request=request
        with self.assertRaisesRegex(RuntimeError,'^Robot safety stop: right tip left the configured workspace$'):
            p.run_session('task',{},SimpleNamespace(_capability=lambda sid:'lease-secret'),
                dict(session_id='session'),lambda:False)
        self.assertEqual(len(calls),3) # submit, poll, Stop; no replay.
        self.assertTrue(calls[-1].endswith('/stop'))

    def test_saved_outcome_remains_failure_with_the_specific_safe_reason(self):
        with tempfile.TemporaryDirectory() as d:
            n=RunNames(Path(d)/'names.sqlite3')
            n.remember_result('ep_workspace',dict(status='stopped',error='RuntimeError: right_tip_outside_workspace at waypoint 0'))
            saved=n.results()['ep_workspace']
            self.assertEqual(saved['result'],'Failure')
            self.assertEqual(saved['errors'],'Robot safety stop: right tip left the configured workspace')
