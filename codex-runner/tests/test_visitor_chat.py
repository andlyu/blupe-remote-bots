"""Real HTTP boundary: separate local runners and hosted visitors share one room."""
import asyncio
from contextlib import contextmanager, ExitStack
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import threading
import time
from urllib import request, error
from unittest.mock import patch

import pytest

from local_playground import LocalPlayground, PUBLIC_SESSION_API, PLAYGROUND
from multi_robot import fleet
from playground import HostedRunner
from remote_yam.session import MockSessionAPI
from remote_yam.visitor_chat import VisitorChat, ChatUnavailable


@contextmanager
def server(factory):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            scope = {'type':'http', 'path':self.path, 'method':self.command,
                     'headers':[(k.lower().encode(), v.encode()) for k,v in self.headers.items()]}
            async def receive():
                return {'type':'http.request', 'body':body}
            sent = []
            async def send(event):
                sent.append(event)
            asyncio.run(app(scope, receive, send))
            self.send_response(sent[0]['status'])
            for key,value in sent[0]['headers']:
                self.send_header(key.decode(), value.decode())
            self.end_headers()
            self.wfile.write(b''.join(event.get('body', b'') for event in sent[1:]))
        do_GET = do_POST = dispatch
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    origin = f'http://127.0.0.1:{http.server_port}'
    app = factory(origin)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield origin, app
    finally:
        http.shutdown(); http.server_close(); thread.join()
        for runner in getattr(app, 'apps', {'default':app}).values():
            for visitor in runner.visitors.values():
                visitor.close()
            shutil.rmtree(runner.root, ignore_errors=True)


class Browser:
    def __init__(self, origin, robot='yam-1'):
        self.origin, self.robot = origin, robot
        self.opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        self.csrf = ''
        self.setup = self.call('/api/session', {})
        self.csrf = self.setup['csrf']

    def call(self, path, payload=None, **headers):
        base = {'Origin':self.origin, 'X-Blupe-Robot':self.robot,
                'Content-Type':'application/json', 'X-YAM-Runner-Token':self.csrf}
        req = request.Request(self.origin + path, headers={**base, **headers},
                              data=None if payload is None else json.dumps(payload).encode())
        return json.load(self.opener.open(req, timeout=10))


def options(origin):
    return dict(public_origin=origin, session_api=None, camera_origin='http://127.0.0.1:1',
                development=True, api_factory=MockSessionAPI)


def test_independent_local_runners_and_hosted_visitors_share_per_robot_reactions():
    robots = [{'id':'yam-1','name':'YAM'}, {'id':'other','name':'Other'}]
    with ExitStack() as stack:
        public, hosted = stack.enter_context(server(lambda origin:fleet(HostedRunner, options(origin), robots)))
        local_a, app_a = stack.enter_context(server(lambda origin:LocalPlayground(visitor_chat_origin=public, **options(origin))))
        local_b, app_b = stack.enter_context(server(lambda origin:LocalPlayground(visitor_chat_origin=public, **options(origin))))
        a, b, h, other = Browser(local_a), Browser(local_b), Browser(public), Browser(public, 'other')
        # These are different cookies, CSRF tokens, processes/runners, and public visitors.
        states = [browser.call('/api/chat') for browser in (a,b,h)]
        assert len({state['visitor'] for state in states}) == 3
        assert a.setup['chat_scope'] == b.setup['chat_scope'] == 'public'
        assert a.csrf != b.csrf != h.csrf
        event = a.call('/api/reactions', {'emoji':'😂'})['reaction']
        for browser in (a,b,h):
            result = browser.call('/api/chat')
            assert result['messages'] == []
            assert [r['id'] for r in result['reactions']] == [event['id']]
            assert result['reactions'][0]['emoji'] == '😂'
            assert a.csrf not in json.dumps(result)
        assert other.call('/api/chat')['reactions'] == []
        assert app_a.reactions.snapshot() == app_b.reactions.snapshot() == []
        # Reverse direction works, and another visitor is not rate-limited by a.
        h.call('/api/reactions', {'emoji':'😠'})
        assert b.call('/api/chat')['reactions'][-1]['emoji'] == '😠'
        with pytest.raises(error.HTTPError) as throttled:
            a.call('/api/reactions', {'emoji':'🙂'})
        assert throttled.value.code == 429
        h.call('/api/chat', {'name':'Viewer', 'text':'Shared hello'})
        for browser in (a,b,h):
            result = browser.call('/api/chat')
            assert result['messages'][0]['text'] == 'Shared hello'
            assert 0 <= result['server_time'] - result['messages'][0]['at'] < 5
        assert app_a.chat_history.messages() == []
        late = Browser(local_a)
        assert late.call('/api/chat')['reactions'] == []
        hosted.apps['yam-1'].reactions.clock = lambda:time.monotonic() + 6
        assert all(browser.call('/api/chat')['reactions'] == [] for browser in (a,b,h))
        # Invalid local CSRF/Origin cannot reach the public relay.
        for headers in ({'X-YAM-Runner-Token':'wrong'}, {'Origin':'https://other.example'}):
            with patch.object(app_a, 'relay_chat') as relay:
                with pytest.raises(error.HTTPError) as denied:
                    a.call('/api/reactions', {'emoji':'🙂'}, **headers)
                assert denied.value.code == 403
                relay.assert_not_called()


def test_public_queue_activates_chat_bridge_but_simulation_and_custom_backend_do_not():
    for api, expected in ((None,None), ('https://custom.example',None), (PUBLIC_SESSION_API,PLAYGROUND)):
        app = LocalPlayground(**{**options('http://127.0.0.1:8791'), 'session_api':api})
        try:
            assert app.visitor_chat_origin == expected
        finally:
            shutil.rmtree(app.root)


def test_relay_does_not_forward_local_credentials_or_follow_redirects():
    chat = VisitorChat('https://public.example', 'yam-1')
    chat.csrf = 'remote-chat-token'
    with patch.object(chat.opener, 'open', side_effect=error.HTTPError(
            'https://public.example/api/reactions', 302, 'redirect', {}, None)) as fetch:
        with pytest.raises(ChatUnavailable):
            chat.publish('/api/reactions', {'emoji':'🙂'})
    req = fetch.call_args.args[0]
    assert req.full_url == 'https://public.example/api/reactions'
    assert req.headers['X-yam-runner-token'] == 'remote-chat-token'
    assert json.loads(req.data) == {'emoji':'🙂'}
    assert 'Cookie' not in req.headers and 'Authorization' not in req.headers
    with pytest.raises(AssertionError):
        chat.publish('/api/run', {})


def test_older_public_release_and_outage_report_failure_without_local_fallback():
    with server(lambda origin:LocalPlayground(visitor_chat_origin='https://public.example', **options(origin))) as (origin, app):
        with patch('remote_yam.visitor_chat.VisitorChat._request', side_effect=ChatUnavailable()):
            browser = Browser(origin)
            assert browser.setup['csrf'] and browser.setup['chat_scope'] == 'public'
            with pytest.raises(error.HTTPError) as failed:
                browser.call('/api/reactions', {'emoji':'🙂'})
            assert failed.value.code == 503
            assert app.reactions.snapshot() == []
            assert browser.call('/api/status')['status'] == 'idle'
    chat = VisitorChat('https://public.example', 'yam-1'); chat.csrf = 'remote'
    with patch.object(chat.opener, 'open', side_effect=error.HTTPError('url',404,'old release',{},None)):
        with pytest.raises(ChatUnavailable) as failed:
            chat.publish('/api/reactions', {'emoji':'🙂'})
        assert 'not available on the public playground yet' in failed.value.message
