"""Real persistence and HTTP-boundary regressions; no provider or robot calls."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
spec=importlib.util.spec_from_file_location('gemini_worker',Path(__file__).resolve().parents[1]/'backend/gemini_worker.py')
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)


async def request(app, path, method='GET', payload=None, headers=None):
    sent=[];body=b'' if payload is None else json.dumps(payload).encode(); consumed=False
    async def receive():
        nonlocal consumed
        if consumed:return {'type':'http.disconnect'}
        consumed=True;return {'type':'http.request','body':body,'more_body':False}
    async def send(message):sent.append(message)
    hs={'content-type':'application/json',**(headers or {})}
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','server':('test',80),'client':('test',1),'headers':[(k.encode(),v.encode()) for k,v in hs.items()]}
    await app(scope,receive,send)
    return next(x['status'] for x in sent if x['type']=='http.response.start'),json.loads(b''.join(x.get('body',b'') for x in sent if x['type']=='http.response.body'))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=w.Store(Path(self.temp.name))
        self.spec=w.RunInput(request_id=uuid.uuid4(),runner_name='Test researcher',email='private@example.test',prompt='Move the block into the cup',mode='simulation')

    def test_run_request_is_idempotent_without_resetting_start_time(self):
        a=self.store.create(self.spec,'a'*64);self.store.event(a['id'],'generating','Generating')
        b=self.store.create(self.spec,'a'*64)
        self.assertEqual(a['created_at'],b['created_at']);self.assertEqual(b['state'],'generating');self.assertEqual(len(self.store.recent()),1)

    def test_request_id_cannot_be_taken_by_another_visitor_or_changed(self):
        self.store.create(self.spec,'a'*64)
        with self.assertRaises(w.HTTPException):self.store.create(self.spec,'b'*64)
        with self.assertRaises(w.HTTPException):self.store.create(self.spec.model_copy(update={'prompt':'Different task'}),'a'*64)

    def test_run_approach_and_execution_mode_are_separate_from_human_identity(self):
        row=self.store.create(self.spec.model_copy(update={'execution_mode':'automated test'}),'a'*64)
        self.assertEqual(row['runner_name'],'Test researcher')
        self.assertEqual(row['configuration']['model'],'Gemini Robotics')
        self.assertEqual(row['configuration']['underlying_models']['coding'],'gemini-4-hydrogen')
        self.assertEqual(row['configuration']['execution_mode'],'automated test')

    def test_request_id_does_not_silently_replace_email_or_execution_mode(self):
        self.store.create(self.spec,'a'*64)
        for update in ({'email':'other@example.test'},{'execution_mode':'automated test'}):
            with self.assertRaises(w.HTTPException):
                self.store.create(self.spec.model_copy(update=update),'a'*64)

    def test_private_email_is_not_in_public_run_fields(self):
        row=self.store.create(self.spec,'a'*64)
        self.assertNotIn('email',json.dumps({k:row[k] for k in w.PUBLIC_FIELDS}))
        self.assertNotIn('private@example.test',json.dumps(row))

    def test_physical_start_rejected_before_persistence_or_dispatch(self):
        app=w.create_app(self.temp.name)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'test-secret'}):
            status,data=asyncio.run(request(app,'/api/runs','POST',{**self.spec.model_dump(mode='json'),'mode':'robot'},{'x-gemini-site-token':'test-secret','x-gemini-visitor':'a'*64}))
        self.assertEqual(status,503);self.assertIn('no robot request submitted',data['detail']);self.assertEqual(self.store.recent(),[])

    def test_stop_and_state_enforce_capability_and_omit_email(self):
        row=self.store.create(self.spec,'a'*64);app=w.create_app(self.temp.name)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'test-secret'}):
            status,_=asyncio.run(request(app,'/api/runs/'+row['id']+'/stop','POST',{}, {'x-gemini-site-token':'test-secret','x-gemini-visitor':'b'*64}));self.assertEqual(status,403)
            status,_=asyncio.run(request(app,'/api/runs/'+row['id']+'/stop','POST',{}, {'x-gemini-site-token':'test-secret','x-gemini-visitor':'a'*64}));self.assertEqual(status,200)
            status,data=asyncio.run(request(app,'/api/state',headers={'x-gemini-site-token':'test-secret','x-gemini-visitor':'a'*64}));self.assertEqual(status,200);self.assertTrue(data['runs'][0]['owned']);self.assertNotIn('private@example.test',json.dumps(data));self.assertEqual(data['runs'][0]['state'],'cancelled')

    def test_billing_failure_is_specific_persistent_and_contains_no_provider_body(self):
        message='System step error (HTTP 402): Your prepayment credits are depleted. secret-provider-body'
        code=w.retain_provider_failure(self.store.root,str(self.spec.request_id),message)
        self.assertEqual(code,'google_prepay_depleted')
        retained=json.loads((self.store.root/'provider-status.json').read_text())
        self.assertNotIn('secret-provider-body',json.dumps(retained))
        with patch.dict(os.environ,{'GEMINI_API_KEY':'synthetic-key'}):
            status=w.runtime_status(Path(self.temp.name),self.store.root)
        self.assertFalse(status['simulation_ready']);self.assertEqual(status['provider_error'],code)
        self.assertIn('credits are depleted',status['message'])
        self.assertIsNone(w.provider_failure_code('HTTP 429 RESOURCE_EXHAUSTED rate limit'))

    def test_worker_requires_site_authentication(self):
        app=w.create_app(self.temp.name)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'test-secret'}):
            status,_=asyncio.run(request(app,'/api/state'))
        self.assertEqual(status,403)

    def test_stop_wins_over_late_completion_or_failure(self):
        row=self.store.create(self.spec,'a'*64)
        self.store.event(row['id'],'cancelled','Stopped by the runner')
        self.store.event(row['id'],'complete','Late provider result')
        self.store.event(row['id'],'failed','Late error')
        self.assertEqual(self.store.get(row['id'])['state'],'cancelled')
        self.assertEqual(self.store.get(row['id'])['progress'],'Stopped by the runner')

    def test_installed_dependencies_do_not_claim_executor_readiness(self):
        root=Path(self.temp.name)
        (root/'mujoco-playground').mkdir()
        (root/'mujoco-playground'/'SKILL.md').write_text('reference')
        with patch.dict(os.environ,{'GEMINI_API_KEY':'configured','GEMINI_EXECUTOR_PROOF':'/nonexistent'}):
            self.assertFalse(w.runtime_status(root)['simulation_ready'])

if __name__=='__main__':unittest.main()
