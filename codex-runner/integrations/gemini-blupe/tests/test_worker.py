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

    def test_worker_requires_site_authentication(self):
        app=w.create_app(self.temp.name)
        with patch.dict(os.environ,{'GEMINI_SITE_TOKEN':'test-secret'}):
            status,_=asyncio.run(request(app,'/api/state'))
        self.assertEqual(status,403)

if __name__=='__main__':unittest.main()
