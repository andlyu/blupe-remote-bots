"""Actual canonical HTTP serializer with a zero-network transport spy."""
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from quiet_session import GeminiSessionAPI,QUIET_PATH
from remote_yam import session


def contract():
    return {'session_create_no_email':{'x-http-path':QUIET_PATH,'x-http-method':'POST',
        'properties':{name:{'type':'boolean','const':False,'default':False}
                      for name in ('email_queue_alert','email_run_video')}}}


class QuietSessionTests(unittest.TestCase):
    def client(self):return GeminiSessionAPI('Test researcher','private@example.test',websocket_factory=object())

    def test_real_serializer_uses_same_queue_with_identity_and_both_emails_disabled(self):
        calls=[]
        def transport(request,**kwargs):
            calls.append(request)
            if request.method=='GET':return io.BytesIO(json.dumps(contract()).encode())
            return io.BytesIO(b'{"session_id":"offline","session_capability":"synthetic-offline-capability"}')
        api=self.client()
        with patch.object(session.request,'urlopen',transport):created=api.create_session('Offline queue contract check',180)
        self.assertEqual([r.full_url.rsplit('/',1)[-1] for r in calls],['contracts','no-email'])
        self.assertIsNone(calls[0].data)
        payload=json.loads(calls[1].data)
        self.assertEqual(payload['runner_name'],'Test researcher');self.assertEqual(payload['email'],'private@example.test')
        self.assertEqual(payload['model'],'Gemini Robotics');self.assertEqual(payload['robot_id'],'yam-1')
        self.assertFalse(payload['email_queue_alert']);self.assertFalse(payload['email_run_video'])
        self.assertEqual(created['session_id'],'offline')
        self.assertEqual(api._session_capabilities['offline'],'synthetic-offline-capability')

    def test_unsupported_or_contradictory_contract_sends_no_identity_or_queue_post(self):
        for value in ({}, {'session_create_no_email':None},{'session_create_no_email':[]},
                      {'session_create_no_email':{'properties':None}},
                      {'session_create_no_email':{'properties':{}}},
                      {'session_create_no_email':{**contract()['session_create_no_email'],'x-http-path':'/v1/sessions'}}):
            with self.subTest(value=value):
                calls=[]
                def transport(request,**kwargs):
                    calls.append(request);return io.BytesIO(json.dumps(value).encode())
                with patch.object(session.request,'urlopen',transport),self.assertRaises(session.SessionAPIError):
                    self.client().create_session('Offline unsupported contract')
                self.assertEqual(len(calls),1);self.assertEqual(calls[0].method,'GET');self.assertIsNone(calls[0].data)

    def test_rollback_after_capability_read_never_falls_back_to_email_endpoint(self):
        calls=[]
        def transport(request,**kwargs):
            calls.append(request)
            if request.method=='GET':return io.BytesIO(json.dumps(contract()).encode())
            raise HTTPError(request.full_url,404,'old API',{},io.BytesIO(b'{"error":{"code":"not_found","message":"unknown session no-email"}}'))
        with patch.object(session.request,'urlopen',transport),self.assertRaises(session.SessionAPIError):
            self.client().create_session('Offline rollback boundary')
        self.assertEqual(len(calls),2)
        self.assertTrue(calls[1].full_url.endswith(QUIET_PATH))
        self.assertFalse(any(r.method=='POST' and r.full_url.endswith('/v1/sessions') for r in calls))

    def test_ambiguous_queue_creation_timeout_is_not_retried(self):
        calls=[]
        def transport(request,**kwargs):
            calls.append(request)
            if request.method=='GET':return io.BytesIO(json.dumps(contract()).encode())
            raise URLError(TimeoutError('offline response ambiguity'))
        with patch.object(session.request,'urlopen',transport),self.assertRaises(session.SessionAPIError):
            self.client().create_session('Offline ambiguous response')
        self.assertEqual(len([r for r in calls if r.method=='POST']),1)

    def test_invalid_attribution_rejected_without_any_transport(self):
        with patch.object(session.request,'urlopen') as transport:
            for name,email in (('','private@example.test'),('automated','private@example.test'),('x'*33,'private@example.test'),('Valid name','invalid'),('Valid\nname','private@example.test'),('Valid name','bad\0@example.test')):
                with self.subTest(name=name),self.assertRaises(ValueError):GeminiSessionAPI(name,email)
        transport.assert_not_called()


if __name__=='__main__':unittest.main()
