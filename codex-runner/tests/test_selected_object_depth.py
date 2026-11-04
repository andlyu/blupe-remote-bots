"""Regression for missing object depth across hosted and saved-run boundaries."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from remote_yam.past_runs import RunNames, merge_run_result, public_runner_diagnostic
from remote_yam.remote_session_policy import RemoteSessionPolicy
from remote_yam.run_errors import public_run_error

MESSAGE = 'No depth for selected object'


class SelectedObjectDepthTests(unittest.TestCase):
    def test_original_worker_error_is_normalized_without_echoing_label(self):
        for error in ('No valid depth for apple', 'ValueError: No valid depth for apple',
                      'RuntimeError: No valid depth for orange block',
                      'No valid depth for object private-key https://private.invalid'):
            self.assertEqual(public_runner_diagnostic({'error': error}), MESSAGE)

    def test_normalized_message_survives_the_second_filter(self):
        for prefix in ('', 'RuntimeError: ', 'ValueError: '):
            self.assertEqual(public_runner_diagnostic({'error': prefix + MESSAGE}), MESSAGE)
            self.assertEqual(public_run_error({'error': prefix + MESSAGE}), MESSAGE)

    def test_hosted_policy_forwards_message_and_still_stops(self):
        policy = RemoteSessionPolicy('http://127.0.0.1:8798', 'secret' * 8,
            provider_name='test', display_name='Private policy', model='right', robot_id='yam-1')
        for error in ('No valid depth for apple', MESSAGE):
            calls = []
            def request(path, payload=None):
                calls.append(path)
                return dict(status='failed', stage='grounding', error=error)
            policy._request = request
            with self.assertRaisesRegex(RuntimeError, '^' + MESSAGE + '$'):
                policy.run_session('task', {}, SimpleNamespace(_capability=lambda sid: 'lease-secret'),
                                   dict(session_id='session'), lambda: False)
            self.assertTrue(calls[-1].endswith('/stop'))

    def test_live_and_saved_results_keep_the_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            names = RunNames(Path(directory) / 'names.sqlite3')
            state = dict(status='stopped', error='RuntimeError: ' + MESSAGE)
            self.assertEqual(public_run_error(state), MESSAGE)
            names.remember_result('ep_depth', state)
            saved = names.results()['ep_depth']
            self.assertEqual(saved['result'], 'Failure')
            self.assertEqual(saved['errors'], MESSAGE)
            self.assertEqual(saved['result_reason'], MESSAGE)
            self.assertEqual(merge_run_result({}, dict(saved, result_reason='Runner or model error'))['result_reason'], MESSAGE)

    def test_other_provider_errors_are_not_exposed_or_misclassified(self):
        for error in (None, {'error': MESSAGE}, 'No valid depth for ',
                      'No valid depth for apple\nprivate-key', MESSAGE + ' private-key',
                      'Unexpected provider response private-key'):
            self.assertIsNone(public_runner_diagnostic({'error': error}))

    def test_missing_frame_keeps_its_distinct_reason(self):
        self.assertEqual(public_runner_diagnostic({'error': 'No fresh RGB-D capture available'}),
                         'No fresh RGB-D capture available')
