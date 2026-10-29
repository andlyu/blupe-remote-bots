import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from station_playground import StationPlayground, loopback_origin
from remote_yam.session import MockSessionAPI


class StationLauncherTests(unittest.TestCase):
    def test_station_flags_select_codex_and_local_storage_without_starting_run(self):
        from run import main
        flags = ['run.py','--station-local','--station-provider','codex','--session-api','http://127.0.0.1:8000',
                 '--camera-origin','http://127.0.0.1:8089','--recording-root','/tmp/station', '--station-episodes-root','/tmp', '--no-browser']
        with patch('sys.argv', flags), patch('run.ensure_codex_runtime'), \
                patch('run.codex_status', return_value={'state':'login_required'}), \
                patch('station_playground.serve') as serve, patch('run.login_codex') as login:
            main()
        args = serve.call_args.args[0]
        self.assertEqual(args.provider, 'codex')
        self.assertTrue(args.no_share_conversation)
        self.assertEqual(args.recording_root, '/tmp/station')
        login.assert_not_called()

    def test_api_station_launch_never_checks_or_installs_codex(self):
        from run import main
        flags = ['run.py','--station-local','--session-api','http://127.0.0.1:8000',
                 '--camera-origin','http://127.0.0.1:8089','--recording-root','/tmp/station', '--station-episodes-root','/tmp', '--no-browser']
        with patch('sys.argv', flags), patch('run.ensure_codex_runtime') as install, \
                patch('run.codex_status') as status, patch('station_playground.serve') as serve:
            main()
        self.assertEqual(serve.call_args.args[0].provider, 'openai')
        install.assert_not_called()
        status.assert_not_called()


class ApiStationTests(unittest.IsolatedAsyncioTestCase):
    async def test_backend_key_never_enters_session_or_queue_payload_and_missing_key_blocks(self):
        from station_credentials import save_openai_key
        from remote_yam.providers import ScriptedAdapter
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); key_file=root/'private/key'
            api=MockSessionAPI(auto_activate=False)
            app=StationPlayground(public_origin='http://127.0.0.1:8787',session_api='http://127.0.0.1:8000',
                camera_origin='http://127.0.0.1:8089',recording_root=root/'logs',
                station_provider='openai',openai_key_file=key_file,hardware_control=True,
                api_factory=lambda:api,provider_factory=lambda *args:ScriptedAdapter([]))
            _,visitor=app.new_visitor()
            try:
                with patch('remote_yam.codex_policy.codex_status') as codex:
                    metadata,_=await app.session_extension({},visitor)
                    self.assertFalse(metadata['station_api_key_ready'])
                    with self.assertRaisesRegex(Exception,'--set-api-key'):
                        app.launch(visitor,{'provider':'openai','prompt':'Test'})
                    save_openai_key('private-fixture-key',key_file)
                    metadata,_=await app.session_extension({},visitor)
                    self.assertTrue(metadata['station_api_key_ready'])
                    self.assertNotIn('private-fixture-key',json.dumps(metadata))
                    self.assertNotIn('codex',metadata)
                    with self.assertRaisesRegex(Exception,'private Jetson terminal'):
                        app.launch(visitor,{'provider':'openai','api_key':'browser-fixture-key','prompt':'Test'})
                    app.launch(visitor,{'provider':'openai','model':'gpt-6-astra','prompt':'Test'})
                    codex.assert_not_called()
                self.assertNotIn('private-fixture-key',json.dumps(api.create_requests))
                app.control(visitor,'/api/stop')
            finally:
                visitor.close()


class StationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.api = MockSessionAPI()
        self.app = self.make_app()
        self.cookie = self.csrf = ''

    def make_app(self):
        return StationPlayground(public_origin='http://127.0.0.1:8787',
            session_api='http://127.0.0.1:8000', camera_origin='http://127.0.0.1:8089',
            recording_root=self.directory.name, api_factory=lambda: self.api,
            hardware_control=True)

    async def asyncTearDown(self):
        for visitor in self.app.visitors.values():
            visitor.close()
        self.directory.cleanup()

    async def call(self, path, payload=None, host='127.0.0.1:8787', csrf=None):
        messages = []
        headers = [(b'host', host.encode()), (b'origin', b'http://127.0.0.1:8787'),
                   (b'content-type', b'application/json'), (b'cookie', self.cookie.encode()),
                   (b'x-yam-runner-token', (self.csrf if csrf is None else csrf).encode())]
        scope = dict(type='http', path=path, method='GET' if payload is None else 'POST', headers=headers)
        async def receive():
            return {'type':'http.request', 'body':json.dumps(payload or {}).encode()}
        async def send(message):
            messages.append(message)
        with patch('remote_yam.subscription_setup.subscription_status', return_value={
                'ready':False, 'state':'login_required', 'message':'Sign in on Jetson'}):
            await self.app(scope, receive, send)
        start = messages[0]
        for key, value in start['headers']:
            if key == b'set-cookie':
                self.cookie = value.decode().split(';')[0]
        body = b''.join(m.get('body', b'') for m in messages[1:])
        content = dict(start['headers']).get(b'content-type', b'')
        return start['status'], json.loads(body) if b'application/json' in content else body, dict(start['headers'])

    async def test_startup_never_queues_or_calls_model_and_browser_has_no_cloud_sources(self):
        with patch('urllib.request.urlopen') as network:
            code, page, headers = await self.call('/')
            self.assertEqual(code, 200)
            self.assertIn(b'data-station-local="true"', page)
            self.assertNotIn(b'src="https://', page)
            self.assertNotIn(b'/synchronized/reader.js', page)
            self.assertIn(b"connect-src 'self'", headers[b'content-security-policy'])
            code, session, _ = await self.call('/api/session', {})
            self.assertEqual(code, 200)
            self.assertTrue(session['station_local'])
            self.assertFalse(session['share_conversation'])
            self.assertIsNone(session['video_stream'])
            network.assert_not_called()
        self.assertEqual(self.api.create_requests, [])

    async def test_media_and_history_do_not_proxy_and_hosts_are_checked(self):
        with patch('urllib.request.urlopen') as network:
            for path in ('/synchronized/index.m3u8', '/live-video/top', '/api/recordings/run_fake/artifacts'):
                code, _, _ = await self.call(path)
                self.assertEqual(code, 404)
            code, body, _ = await self.call('/api/past-runs')
            self.assertEqual((code, body['runs']), (200, []))
            self.assertEqual((await self.call('/api/past-runs', host='other.example'))[0], 421)
            network.assert_not_called()

    def test_readiness_uses_local_operator_without_the_cloud_tunnel(self):
        with patch('remote_yam.operator_status.read_auto_queue', return_value={'enabled':False}) as readiness:
            self.app.refresh_monitor()
        readiness.assert_called_once_with('http://127.0.0.1:8096')
        self.assertFalse(self.app.operator_auto_queue['enabled'])

    async def test_recordings_survive_disconnect_lifespan_shutdown_and_new_browser(self):
        _, session, _ = await self.call('/api/session', {})
        self.csrf = session['csrf']
        visitor = next(iter(self.app.visitors.values()))
        run_id = 'run_' + 'a'*32
        log = visitor.directory / run_id / 'interactions.jsonl'
        log.parent.mkdir()
        log.write_text('{"kind":"lifecycle","message":"Stopped locally","details":{}}\n')
        self.assertEqual((await self.call('/api/disconnect', {}))[0], 200)
        await asyncio.gather(*self.app.cleanups)
        events = iter([{'type':'lifespan.startup'}, {'type':'lifespan.shutdown'}])
        async def receive(): return next(events)
        async def send(event): pass
        await self.app({'type':'lifespan'}, receive, send)
        self.assertTrue(log.is_file())
        self.app = self.make_app()
        self.cookie = self.csrf = ''
        await self.call('/api/session', {})
        code, body, _ = await self.call('/api/recordings')
        self.assertEqual(code, 200)
        self.assertEqual(body['runs'][0]['run_id'], run_id)
        code, body, _ = await self.call('/api/recordings/'+run_id+'/interactions')
        self.assertEqual(code, 200)
        self.assertEqual(body['events'][0]['message'], 'Stopped locally')

    async def test_provider_and_csrf_cannot_bypass_local_mode(self):
        _, session, _ = await self.call('/api/session', {})
        self.csrf = session['csrf']
        for provider in ('openai', 'groot', 'local_raise_lower', 'claude'):
            code, _, _ = await self.call('/api/run', {'provider':provider, 'prompt':'Test'})
            self.assertEqual(code, 400)
        self.assertEqual((await self.call('/api/stop', {}, csrf='invalid'))[0], 403)
        self.assertEqual((await self.call('/api/stop', {}))[0], 200)
        self.assertEqual(self.api.create_requests, [])

    def test_remote_transport_and_url_credentials_are_rejected(self):
        for value in ('https://playground.blupe.io', 'http://10.1.10.185:8000',
                      'http://127.0.0.1:8000/path', 'http://user@127.0.0.1:8000',
                      'http://127.0.0.1:8000?cloud=1'):
            with self.assertRaises(ValueError): loopback_origin(value)


if __name__ == '__main__':
    unittest.main()
