"""Public local launches retain the hosted map and provenance, never credentials."""
import asyncio
import json
import shutil
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, MagicMock, patch

from local_playground import LocalPlayground, PLAYGROUND, PUBLIC_SESSION_API
from remote_yam.session import MockSessionAPI


class LocalPublicCloudTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = LocalPlayground(public_origin='http://127.0.0.1:8791',
            session_api=PUBLIC_SESSION_API, camera_origin='http://127.0.0.1:8089',
            development=True, api_factory=MockSessionAPI)
        self.app.robot_id = 'robot-robohouse'

    async def asyncTearDown(self):
        for visitor in self.app.visitors.values():
            await asyncio.to_thread(visitor.close)
        shutil.rmtree(self.app.root, ignore_errors=True)

    async def call(self, path, *, query=b'', method='GET', host='127.0.0.1:8791'):
        messages = []
        async def receive():
            return {'type':'http.request', 'body':b''}
        async def send(message):
            messages.append(message)
        await self.app({'type':'http', 'path':path, 'method':method,
            'query_string':query, 'headers':[(b'host',host.encode()),
                (b'cookie',b'local-session'), (b'authorization',b'Bearer private-key'),
                (b'x-yam-runner-token',b'local-token')]}, receive, send)
        return messages[0]['status'], b''.join(m.get('body',b'') for m in messages[1:])

    async def test_public_catalog_retains_model_coordinates_and_filters(self):
        payload = {'runs':[{'episode_id':'ep_example','model':'dream-1',
            'xyz':[.1,.2,.3]}], 'cloud':{'version':'frozen-map'}, 'models':['dream-1']}
        body = json.dumps(payload).encode()
        response = MagicMock(status=200, headers={'Content-Type':'application/json'})
        response.__enter__.return_value = response
        response.read.return_value = body
        with patch('local_playground.request.urlopen', return_value=response) as fetch:
            code, actual = await self.call('/api/run-catalog',
                query=b'view=cloud&model=dream-1&q=stack&robot_id=wrong')
        self.assertEqual((code, actual), (200, body))
        request = fetch.call_args.args[0]
        self.assertEqual(urlsplit(request.full_url).scheme+'://'+urlsplit(request.full_url).netloc, PLAYGROUND)
        self.assertEqual(parse_qs(urlsplit(request.full_url).query),
            {'view':['cloud'],'model':['dream-1'],'q':['stack'],'robot_id':['robot-robohouse']})
        for name in ('Cookie','Authorization','X-yam-runner-token'):
            self.assertIsNone(request.get_header(name))
        self.assertEqual(request.get_header('Origin'), PLAYGROUND)

    async def test_label_payload_keeps_prediction_and_human_provenance_unchanged(self):
        body = b'{"version":1,"runs":[{"episode_id":"ep_example","auto":{"label":"Failure","model":"review-model"},"human":null}]}'
        response = MagicMock(status=200, headers={'Content-Type':'application/json'})
        response.__enter__.return_value = response
        response.read.return_value = body
        with patch('local_playground.request.urlopen', return_value=response) as fetch:
            self.assertEqual(await self.call('/api/run-labels'), (200, body))
        self.assertEqual(fetch.call_args.args[0].full_url, PLAYGROUND+'/api/run-labels')

    async def test_public_cloud_is_read_only_and_checks_host_before_upstream(self):
        with patch('local_playground.request.urlopen') as fetch:
            for path in ('/api/run-catalog','/api/run-labels'):
                for method in ('POST','PATCH','DELETE'):
                    self.assertEqual((await self.call(path,method=method))[0],403)
                self.assertEqual((await self.call(path,host='other.example'))[0],421)
            fetch.assert_not_called()

    async def test_custom_or_simulated_backend_keeps_its_catalog_even_with_public_chat(self):
        for origin in (None, 'https://custom-robot.example'):
            app = LocalPlayground(public_origin='http://127.0.0.1:8791',
                session_api=origin, camera_origin='http://127.0.0.1:8089',
                visitor_chat_origin=PLAYGROUND, development=True, api_factory=MockSessionAPI)
            try:
                with patch('playground.HostedRunner.http', new_callable=AsyncMock) as local, \
                     patch('local_playground.request.urlopen') as fetch:
                    for path in ('/api/run-catalog','/api/run-labels'):
                        await app.http({'path':path,'method':'GET'},None,None)
                    self.assertEqual(local.await_count,2)
                    fetch.assert_not_called()
            finally:
                shutil.rmtree(app.root,ignore_errors=True)

    async def test_upstream_failure_is_explicit_instead_of_fabricated_empty_labels(self):
        with patch('local_playground.request.urlopen',side_effect=OSError('private upstream detail')):
            code, body = await self.call('/api/run-labels')
        self.assertEqual(code,503)
        self.assertIn(b'Public viewer temporarily unavailable',body)
        self.assertNotIn(b'private upstream detail',body)
