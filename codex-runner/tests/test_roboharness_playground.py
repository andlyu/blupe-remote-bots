"""Admission and release gates use the production wrapper without robot traffic."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,AsyncMock,Mock
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playground import RequestError
from roboharness_playground import RoboHarnessPlayground,verify_release
from roboharness_preflight import ROOT,source_inventory
from remote_yam.controller import RunnerController
from remote_yam.session import MockSessionAPI,SCHEMA_VERSION
from remote_yam.run_changes import snapshot
from remote_yam.past_runs import RunNames


class PlaygroundTests(unittest.TestCase):
    def test_confirmed_human_and_approach_required_before_provider_or_queue(self):
        app=object.__new__(RoboHarnessPlayground)
        good=dict(provider='roboharness',model='RoboHarness',runner_name='Synthetic runner',email='synthetic@example.invalid',execution_mode='automated_verification')
        app.validate_launch(None,good,False)
        for change in ({'runner_name':'Automated'},{'runner_name':''},{'email':''},{'email':'a b@example.invalid'},
                       {'provider':'codex'},{'model':'gpt-6-astra'},{'execution_mode':'invented'},
                       {'api_key':'synthetic'},{'endpoint':'https://other.invalid'},{'executor':'other'},{'system_prompt':'override'},
                       {'grounding_camera':'external'},{'grounding_camera':None},{'grounding_camera':True}):
            with self.subTest(change=change),self.assertRaises(RequestError):app.validate_launch(None,{**good,**change},False)

    def test_replay_observer_starts_only_after_acceptance_and_cannot_cancel_accepted_run(self):
        app=object.__new__(RoboHarnessPlayground);app.public_replays=Mock()
        visitor=SimpleNamespace(controller=Mock());payload={'runner_name':'Synthetic runner'}
        receipt={'ok':True,'attempt_id':'offline_attempt','status':'queued'}
        with patch('playground.HostedRunner.launch',return_value=receipt):
            self.assertEqual(app.launch(visitor,payload),receipt)
            app.public_replays.start.assert_called_once_with(visitor.controller)
        app.public_replays.reset_mock();app.public_replays.start.side_effect=RuntimeError('synthetic private diagnostic')
        with patch('playground.HostedRunner.launch',return_value=receipt):
            self.assertEqual(app.launch(visitor,payload),receipt)
        self.assertNotIn('synthetic private diagnostic',str(visitor.controller._interactions.add.call_args))
        app.public_replays.reset_mock()
        with patch('playground.HostedRunner.launch',side_effect=RequestError(503,'Synthetic admission failure')):
            with self.assertRaises(RequestError):app.launch(visitor,payload)
        app.public_replays.start.assert_not_called()

    def test_lifecycle_source_timing_retains_only_evidence_fields(self):
        controller=RunnerController(MockSessionAPI())
        controller._session_id='synthetic'
        controller._handle_event(dict(schema_version=SCHEMA_VERSION,session_id='synthetic',
            type='lifecycle',timestamp=123.25,payload=dict(state='queued',reason='unit_test',
                position=2,session_capability='synthetic-secret',email='synthetic@example.invalid')))
        event=controller.status()['run_summary']['events'][-1]
        self.assertEqual(event,dict(type='lifecycle',timestamp=123.25,state='queued',reason='unit_test',position=2))

    def test_queue_entry_source_time_is_retained_once_for_the_owned_session_only(self):
        controller=RunnerController(MockSessionAPI());controller._session_id='synthetic';controller._status='queued'
        response=dict(schema_version=SCHEMA_VERSION,type='queue_snapshot',generated_at=125,stations=[],entries=[
            dict(position=1,session_id='synthetic',status='queued',created_at=123.25,email='synthetic@example.invalid',session_capability='synthetic-secret'),
            dict(position=2,session_id='other',status='queued',created_at=124)])
        controller.update_queue_snapshot(response)
        first=controller.status()['run_summary']['events']
        self.assertEqual(first,[dict(type='queue_entry',timestamp=123.25,state='queued',position=1,source='queue_snapshot')])
        response['entries'][0]['created_at']=999
        controller.update_queue_snapshot(response)
        self.assertEqual(controller.status()['run_summary']['events'],first)
        self.assertNotIn('synthetic-secret',json.dumps(first));self.assertNotIn('synthetic@example.invalid',json.dumps(first))

    def test_run_snapshot_keeps_models_runner_and_execution_mode_separate(self):
        config=dict(model='RoboHarness',provider='roboharness',underlying_models=dict(planning='gpt-6-astra',vision='gpt-6-astra',resolved=None),runner_name='Synthetic runner',execution_mode='automated_verification',email='synthetic@example.invalid',api_key='synthetic-secret')
        stored=snapshot(SimpleNamespace(public_config=lambda:config),'offline task',60)
        self.assertEqual(stored['underlying_models'],config['underlying_models'])
        self.assertEqual(stored['runner_name'],'Synthetic runner')
        self.assertEqual(stored['execution_mode'],'automated_verification')
        self.assertNotIn('synthetic@example.invalid',json.dumps(stored));self.assertNotIn('synthetic-secret',json.dumps(stored))

    def test_public_episode_config_filters_station_approach_and_private_fields(self):
        with tempfile.TemporaryDirectory() as d:
            names=RunNames(Path(d)/'runs.sqlite3')
            names.remember_metadata('ep_synthetic','yam-1','offline task',123,dict(model='RoboHarness',runner_name='Synthetic runner',underlying_models={'planning':'gpt-6-astra','resolved':None},email='synthetic@example.invalid',session_capability='synthetic-secret'))
            app=object.__new__(RoboHarnessPlayground);app.run_names=names;app.robot_id='yam-1';app.json=AsyncMock()
            def query(episode):
                return asyncio.run(app.public_extension(dict(method='GET',path='/api/roboharness/run-config',query_string=('episode_id='+episode).encode()),None,None,{}))
            self.assertTrue(query('ep_synthetic'));body=app.json.call_args.args[2]
            self.assertEqual(body['configuration']['underlying_models']['planning'],'gpt-6-astra')
            self.assertNotIn('synthetic@example.invalid',json.dumps(body));self.assertNotIn('synthetic-secret',json.dumps(body))
            app.robot_id='robot-ba8413962083809c';query('ep_synthetic');self.assertEqual(app.json.call_args.args[1],404)
            query('../../other');self.assertEqual(app.json.call_args.args[1],404)

    def test_preflight_requires_clean_pass_and_complete_unchanged_source_inventory(self):
        receipt=dict(status='passed',tests_run=70,dirty_source=False,
            source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_inventory()})
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'receipt.json'
            path.write_text(json.dumps(receipt));self.assertEqual(verify_release(path)['status'],'passed')
            variants=[{**receipt,'tests_run':65},{**receipt,'dirty_source':True},{**receipt,'status':'draft_passed'},
                {**receipt,'source_sha256':{}},{**receipt,'source_sha256':{**receipt['source_sha256'],'src/remote_yam/roboharness_control.py':'stale'}}]
            for value in variants:
                path.write_text(json.dumps(value))
                with self.subTest(value=value.get('status')),self.assertRaises(ValueError):verify_release(path)


if __name__=='__main__':unittest.main()
