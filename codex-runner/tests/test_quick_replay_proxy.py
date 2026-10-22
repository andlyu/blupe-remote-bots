import asyncio
import io
import shutil
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from local_playground import LocalPlayground, PLAYGROUND
from remote_yam.session import MockSessionAPI


class QuickReplayProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = LocalPlayground(public_origin='http://127.0.0.1:8791',
            session_api=None, camera_origin='http://127.0.0.1:8089',
            development=True, api_factory=MockSessionAPI)
        self.path = '/api/quick-replays/ep_example/' + 'a' * 64 + '.mp4'

    async def asyncTearDown(self):
        for visitor in self.app.visitors.values():
            await asyncio.to_thread(visitor.close)
        shutil.rmtree(self.app.root, ignore_errors=True)

    async def call(self, *, path=None, method='GET', host='127.0.0.1:8791', headers=()):
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': b''}
        async def send(message):
            messages.append(message)
        await self.app({'type': 'http', 'path': path or self.path, 'method': method,
            'query_string': b'', 'headers': [(b'host', host.encode()), *headers]}, receive, send)
        return (messages[0]['status'], dict(messages[0]['headers']),
                b''.join(m.get('body', b'') for m in messages[1:]))

    def response(self, body, status=200, **headers):
        response = MagicMock(status=status, headers={'Content-Type': 'video/mp4', **headers})
        response.__enter__.return_value = response
        response.read.return_value = body
        return response

    async def test_local_playback_forwards_seeking_without_browser_credentials(self):
        response = self.response(b'clip', status=206, **{
            'Content-Range': 'bytes 4-7/20', 'Accept-Ranges': 'bytes', 'ETag': '"verified"'})
        with patch('local_playground.request.urlopen', return_value=response) as upstream:
            code, headers, body = await self.call(headers=[(b'range', b'bytes=4-7'),
                (b'cookie', b'local-session'), (b'authorization', b'Bearer local-secret')])
        self.assertEqual((code, body), (206, b'clip'))
        self.assertEqual(headers[b'content-range'], b'bytes 4-7/20')
        self.assertEqual(headers[b'accept-ranges'], b'bytes')
        self.assertEqual(headers[b'etag'], b'"verified"')
        request = upstream.call_args.args[0]
        self.assertEqual(request.full_url, PLAYGROUND + self.path)
        self.assertEqual(request.get_header('Range'), 'bytes=4-7')
        self.assertIsNone(request.get_header('Cookie'))
        self.assertIsNone(request.get_header('Authorization'))
        self.assertEqual(upstream.call_count, 1)

    async def test_preview_larger_than_generic_viewer_limit_is_playable(self):
        clip = b'x' * 9_000_000
        with patch('local_playground.request.urlopen', return_value=self.response(clip)):
            code, _, body = await self.call()
        self.assertEqual((code, len(body)), (200, len(clip)))

    async def test_unavailable_and_invalid_range_responses_keep_their_status(self):
        for status, headers in [(404, {}), (416, {'Content-Range': 'bytes */20'})]:
            upstream_error = HTTPError(PLAYGROUND + self.path, status, 'Unavailable',
                {'Content-Type': 'video/mp4', **headers}, io.BytesIO(b''))
            with patch('local_playground.request.urlopen', side_effect=upstream_error) as upstream:
                code, actual, _ = await self.call()
            self.assertEqual(code, status)
            self.assertEqual(upstream.call_count, 1)
            if status == 416:
                self.assertEqual(actual[b'content-range'], b'bytes */20')

    async def test_proxy_is_read_only_and_accepts_only_valid_replay_paths(self):
        with patch('local_playground.request.urlopen') as upstream:
            self.assertEqual((await self.call(method='POST'))[0], 403)
            self.assertEqual((await self.call(host='other.example'))[0], 421)
            # Unknown paths retain the runner's ordinary visitor authentication.
            self.assertEqual((await self.call(path='/api/quick-replays/ep_example/not-a-hash.mp4'))[0], 401)
            upstream.assert_not_called()

    async def test_cache_size_limit_and_connection_failure_are_bounded_errors(self):
        for result in [self.response(b'x' * (16 * 1024 * 1024 + 1)), OSError('private upstream detail')]:
            options = {'side_effect': result} if isinstance(result, OSError) else {'return_value': result}
            with patch('local_playground.request.urlopen', **options):
                code, _, body = await self.call()
            self.assertEqual(code, 503)
            self.assertNotIn(b'private upstream detail', body)
