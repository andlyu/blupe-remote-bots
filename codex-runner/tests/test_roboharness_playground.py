"""Admission and release gates use the production wrapper without robot traffic."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playground import RequestError
from roboharness_playground import RoboHarnessPlayground,verify_release
from roboharness_preflight import ROOT,source_inventory
from remote_yam.controller import RunnerController
from remote_yam.session import MockSessionAPI,SCHEMA_VERSION


class PlaygroundTests(unittest.TestCase):
    def test_confirmed_human_and_approach_required_before_provider_or_queue(self):
        app=object.__new__(RoboHarnessPlayground)
        good=dict(provider='roboharness',model='RoboHarness',runner_name='Synthetic runner',email='synthetic@example.invalid',execution_mode='automated_verification')
        app.validate_launch(None,good,False)
        for change in ({'runner_name':'Automated'},{'runner_name':''},{'email':''},{'email':'a b@example.invalid'},
                       {'provider':'codex'},{'model':'gpt-6-astra'},{'execution_mode':'invented'},
                       {'api_key':'synthetic'},{'endpoint':'https://other.invalid'},{'executor':'other'},{'system_prompt':'override'}):
            with self.subTest(change=change),self.assertRaises(RequestError):app.validate_launch(None,{**good,**change},False)

    def test_lifecycle_source_timing_retains_only_evidence_fields(self):
        controller=RunnerController(MockSessionAPI())
        controller._session_id='synthetic'
        controller._handle_event(dict(schema_version=SCHEMA_VERSION,session_id='synthetic',
            type='lifecycle',timestamp=123.25,payload=dict(state='queued',reason='unit_test',
                position=2,session_capability='synthetic-secret',email='synthetic@example.invalid')))
        event=controller.status()['run_summary']['events'][-1]
        self.assertEqual(event,dict(type='lifecycle',timestamp=123.25,state='queued',reason='unit_test',position=2))

    def test_preflight_requires_clean_pass_and_complete_unchanged_source_inventory(self):
        receipt=dict(status='passed',tests_run=21,dirty_source=False,
            source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_inventory()})
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'receipt.json'
            path.write_text(json.dumps(receipt));self.assertEqual(verify_release(path)['status'],'passed')
            variants=[{**receipt,'dirty_source':True},{**receipt,'status':'draft_passed'},
                {**receipt,'source_sha256':{}},{**receipt,'source_sha256':{**receipt['source_sha256'],'src/remote_yam/roboharness_control.py':'stale'}}]
            for value in variants:
                path.write_text(json.dumps(value))
                with self.subTest(value=value.get('status')),self.assertRaises(ValueError):verify_release(path)


if __name__=='__main__':unittest.main()
