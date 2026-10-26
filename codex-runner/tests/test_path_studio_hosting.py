"""Hosted ingress checks with a stub planner; no network to robot services."""
import base64
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from urllib import request, error, parse

spec = importlib.util.spec_from_file_location('studio_hosting', Path(__file__).parents[1]/'path_studio.py')
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)


class StubService:
    identity = {'runner_name': 'Test owner', 'email': 'owner@example.test'}
    calls = []

    def simulate(self, body):
        self.calls.append(body)
        return {'verified': True}

    def status(self, station):
        return {'run':getattr(self,'run_state',None)}

    def run(self, body):
        self.run_state={'identity':body['identity'],'status':'queued'}
        return {'run':self.run_state}

    def stop(self):
        self.run_state=None
        return {'run':None}

    def close(self):
        self.stop()


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.service = StubService()
        self.service.calls = []
        self.password = 'test-password-at-least-24-characters'
        self.server = studio.create_server(0, self.service, public_origin='https://draw.example.test',
                                           username='Andrew', password=self.password, base_path='/path-studio/',
                                           origin_mounts={'https://neutral.example.test':'/'})
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.auth = 'Basic '+base64.b64encode(f'Andrew:{self.password}'.encode()).decode()

    def fetch(self, path, headers=None, body=None):
        return request.urlopen(request.Request(self.base+path, data=body,
            headers={'Host':'draw.example.test', **(headers or {})}))

    def test_private_assets_identity_and_stream_require_owner_login(self):
        for path in ('/', '/path-studio-api.js', '/api/path-studio/config',
                     '/api/path-studio/status', '/api/path-studio/video/robo-house/index.m3u8'):
            for headers in ({}, {'Authorization': 'Basic invalid'}):
                with self.assertRaises(error.HTTPError) as caught:
                    self.fetch(path, headers)
                self.assertEqual(caught.exception.code, 401)
                self.assertEqual(caught.exception.headers['Referrer-Policy'],'same-origin')
        with self.fetch('/api/path-studio/config', {'Authorization':self.auth}) as response:
            self.assertEqual(json.load(response)['identity'], self.service.identity)

    def test_https_origin_csrf_host_and_fetch_site_remain_enforced(self):
        headers = {'Authorization': self.auth, 'Origin': 'https://draw.example.test',
                   'Content-Type':'application/json', 'X-Path-Studio-Token':self.server.csrf_token}
        with self.fetch('/api/path-studio/simulate', headers, b'{}') as response:
            self.assertTrue(json.load(response)['verified'])
        for change in ({'Origin':'https://evil.example'}, {'Host':'evil.example'},
                       {'Sec-Fetch-Site':'cross-site'}, {'X-Path-Studio-Token':'wrong'},
                       {'Origin':'http://draw.example.test', 'X-Forwarded-Proto':'https'}):
            with self.assertRaises(error.HTTPError) as caught:
                self.fetch('/api/path-studio/simulate', {**headers, **change}, b'{}')
            self.assertEqual(caught.exception.code,403)
        self.assertEqual(self.service.calls,[{}])

    def test_health_check_exposes_no_session_or_identity(self):
        with self.fetch('/healthz') as response:
            self.assertEqual(json.load(response), {'status':'ok'})

    def test_neutral_origin_keeps_its_own_cookie_mount_and_csrf_origin(self):
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        body=parse.urlencode({'username':'Andrew','password':self.password}).encode()
        headers={'Host':'neutral.example.test','Origin':'https://neutral.example.test',
                 'Content-Type':'application/x-www-form-urlencoded'}
        with self.assertRaises(error.HTTPError) as caught:
            request.build_opener(NoRedirect()).open(request.Request(self.base+'/login',body,headers))
        self.assertEqual(caught.exception.code,303)
        self.assertEqual(caught.exception.headers['Location'],'/')
        cookie=caught.exception.headers['Set-Cookie']
        self.assertIn('; Path=/;',cookie)
        controls={'Host':'neutral.example.test','Origin':'https://neutral.example.test',
                  'Cookie':cookie.split(';')[0],'Content-Type':'application/json',
                  'X-Path-Studio-Token':self.server.csrf_token}
        with self.fetch('/api/path-studio/simulate',controls,b'{}') as response:
            self.assertTrue(json.load(response)['verified'])
        with self.assertRaises(error.HTTPError) as caught:
            self.fetch('/api/path-studio/simulate',{**controls,'Origin':'https://draw.example.test'},b'{}')
        self.assertEqual(caught.exception.code,403)
        self.assertEqual(self.service.calls,[{}])

    def test_login_uses_private_cookie_and_rejects_cross_site_forms(self):
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        body = parse.urlencode({'username':'Andrew','password':self.password}).encode()
        headers = {'Host':'draw.example.test','Origin':'https://draw.example.test',
                   'Content-Type':'application/x-www-form-urlencoded'}
        req = request.Request(self.base+'/login',body,headers)
        with self.assertRaises(error.HTTPError) as caught:
            request.build_opener(NoRedirect()).open(req)
        response = caught.exception
        self.assertEqual(response.code,303)
        cookie = response.headers['Set-Cookie']
        for flag in ('Secure','HttpOnly','SameSite=Strict'):
            self.assertIn(flag,cookie)
        with self.fetch('/api/path-studio/config', {'Cookie':cookie.split(';')[0]}) as result:
            self.assertEqual(json.load(result)['identity'],self.service.identity)
        for origin in ('https://evil.example', 'http://draw.example.test'):
            with self.assertRaises(error.HTTPError) as caught:
                self.fetch('/login', {**headers, 'Origin':origin}, body)
            self.assertEqual(caught.exception.code,403)
        with self.assertRaises(error.HTTPError) as caught:
            self.fetch('/login', headers, b'username=Andrew&password=wrong')
        self.assertEqual(caught.exception.code,401)
        self.assertIn(b'did not match',caught.exception.read())

    def test_public_binding_cannot_silently_disable_authentication(self):
        for kwargs in ({'bind':'0.0.0.0'}, {'public_origin':'http://draw.example.test'},
                       {'public_origin':'https://draw.example.test'},
                       {'public_origin':'https://draw.example.test/path'},
                       {'public_origin':'https://draw.example.test','username':'Andrew','password':'short'}):
            with self.assertRaises(ValueError):
                studio.create_server(0, self.service, **kwargs)




class PublicVisitorTests(unittest.TestCase):
    def setUp(self):
        self.owner=StubService()
        def factory(key):
            service=StubService();service.identity={'runner_name':'','email':''};service.calls=[]
            return service
        self.server=studio.create_server(0,self.owner,public_origin='https://owner.example.test',
            username='Andrew',password='test-owner-password-more-than24chars',
            origin_mounts={'https://shared.example.test':'/'},public_origins=['https://shared.example.test'],
            visitor_factory=factory)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.visitors.close);self.addCleanup(self.server.shutdown)
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def fetch(self,path,cookie=None,token=None,body=None,extra=None):
        headers={'Host':'shared.example.test'}
        if cookie:headers['Cookie']=cookie
        if token:headers['X-Path-Studio-Token']=token
        if body is not None:headers.update({'Origin':'https://shared.example.test','Content-Type':'application/json'})
        headers.update(extra or {})
        return request.urlopen(request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers))

    def connect(self,cookie=None):
        with self.fetch('/api/path-studio/config',cookie) as r:
            value=json.load(r);new_cookie=r.headers.get('Set-Cookie')
        self.assertEqual(value['identity'],{'runner_name':'','email':''})
        if new_cookie:
            for flag in ('Secure','HttpOnly','SameSite=Strict'):self.assertIn(flag,new_cookie)
        return (new_cookie.split(';')[0] if new_cookie else cookie),value['csrf_token']

    def test_shared_workspace_opens_without_login_and_private_origin_stays_private(self):
        with self.fetch('/') as response:
            html=response.read();self.assertEqual(response.status,200)
            self.assertIn(b'<title>Path Studio</title>',html);self.assertNotIn(b'password',html)
        with self.assertRaises(error.HTTPError) as caught:
            self.fetch('/',extra={'Host':'owner.example.test'})
        self.assertEqual(caught.exception.code,401)

    def test_identity_run_and_stop_are_isolated_across_browsers(self):
        a,ta=self.connect();b,tb=self.connect();self.assertNotEqual(a,b);self.assertNotEqual(ta,tb)
        self.assertEqual(self.connect(a),(a,ta))
        identity={'runner_name':'Visitor One','email':'one@example.test'}
        with self.fetch('/api/path-studio/run',a,ta,{'identity':identity}) as r:
            self.assertEqual(json.load(r)['run']['identity'],identity)
        with self.fetch('/api/path-studio/status',b) as r:self.assertIsNone(json.load(r)['run'])
        with self.fetch('/api/path-studio/stop',b,tb,{}) as r:self.assertIsNone(json.load(r)['run'])
        with self.fetch('/api/path-studio/status',a) as r:self.assertEqual(json.load(r)['run']['identity'],identity)
        self.assertIsNone(self.owner.status('robohouse')['run'])
        for cookie,token in ((None,ta),(b,ta),(a,tb)):
            with self.assertRaises(error.HTTPError) as caught:self.fetch('/api/path-studio/stop',cookie,token,{})
            self.assertEqual(caught.exception.code,403)
        with self.assertRaises(error.HTTPError) as caught:
            self.fetch('/api/path-studio/stop',a,ta,{},extra={'Origin':'https://evil.example'})
        self.assertEqual(caught.exception.code,403)

    def test_expired_inactive_session_is_replaced_without_restoring_owner_identity(self):
        cookie,token=self.connect()
        for record in self.server.visitors.entries.values():record['seen']-=3600
        self.server.visitors.prune()
        new_cookie,new_token=self.connect(cookie)
        self.assertNotEqual(cookie,new_cookie);self.assertNotEqual(token,new_token)


if __name__ == '__main__':
    unittest.main()
