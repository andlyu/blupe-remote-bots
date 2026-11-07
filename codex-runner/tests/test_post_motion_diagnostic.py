import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from remote_yam.past_runs import RunNames, public_runner_diagnostic
from remote_yam.remote_session_policy import RemoteSessionPolicy
from remote_yam.run_errors import public_run_error

UNKNOWN='Motion completed; placement verification was inconclusive'
FAILED='Motion completed; requested placement was not achieved'


class PostMotionDiagnosticTests(unittest.TestCase):
    def test_fixed_reasons_survive_both_filter_passes(self):
        for message in (UNKNOWN,FAILED):
            for prefix in ('','RuntimeError: ','ValueError: '):
                with self.subTest(message=message,prefix=prefix):
                    self.assertEqual(public_runner_diagnostic({'error':prefix+message}),message)
                    self.assertEqual(public_run_error({'error':prefix+message}),message)
                    self.assertIsNone(public_runner_diagnostic({'error':prefix+message+' private detail'}))

    def test_hosted_adapter_preserves_reason_and_still_stops(self):
        for message in (UNKNOWN,FAILED):
            policy=RemoteSessionPolicy('http://127.0.0.1:8798','secret'*8,
                provider_name='private',display_name='Private policy',model='right',robot_id='yam-1')
            calls=[]
            def request(path,payload=None):
                calls.append(path);return dict(status='failed',error=message,stage='verifying')
            policy._request=request
            with self.assertRaisesRegex(RuntimeError,'^'+message+'$'):
                policy.run_session('task',{},SimpleNamespace(_capability=lambda sid:'lease-secret'),
                    dict(session_id='session'),lambda:False)
            self.assertTrue(calls[-1].endswith('/stop'))

    def test_inconclusive_is_unknown_but_observed_task_failure_is_failure(self):
        with tempfile.TemporaryDirectory() as d:
            names=RunNames(Path(d)/'names.sqlite3')
            for i,(message,label) in enumerate(((UNKNOWN,'Unknown'),(FAILED,'Failure'))):
                names.remember_result('ep_verify_'+str(i),dict(status='stopped',error='RuntimeError: '+message))
                saved=names.results()['ep_verify_'+str(i)]
                self.assertEqual(saved['result'],label)
                self.assertEqual(saved['result_reason'],message)
                self.assertEqual(saved['errors'],None if label=='Unknown' else message)

    def test_real_safety_failure_overrides_visual_uncertainty(self):
        with tempfile.TemporaryDirectory() as d:
            names=RunNames(Path(d)/'names.sqlite3')
            names.remember_result('ep_safety',dict(status='stopped',error=UNKNOWN,
                safety_error={'code':'physical_execution_failure'}))
            self.assertEqual(names.results()['ep_safety']['result'],'Failure')
