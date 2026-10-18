"""The optional viewer assets are same-origin and narrowly served."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import playground

class SuperResolutionAssets(unittest.IsolatedAsyncioTestCase):
    async def request(self,path):
        app=playground.HostedRunner.__new__(playground.HostedRunner)
        app.authority='robot.example';app.secure=True
        messages=[]
        async def send(message):messages.append(message)
        await app.http({'path':path,'method':'GET','headers':[(b'host',b'robot.example')]},None,send)
        return messages

    async def test_model_and_worker_have_correct_types_and_worker_csp(self):
        for name,kind in [('fsrcnn-x2-fp16.onnx',b'application/octet-stream'),
                          ('worker.js',b'text/javascript'),('viewer.css',b'text/css')]:
            messages=await self.request('/static/super-resolution/'+name)
            self.assertEqual(messages[0]['status'],200)
            headers=dict(messages[0]['headers'])
            self.assertEqual(headers[b'content-type'],kind)
            self.assertIn(b"'wasm-unsafe-eval'",headers[b'content-security-policy'])
            self.assertIn(b"worker-src 'self'",headers[b'content-security-policy'])
            self.assertNotIn(b"'unsafe-eval'",headers[b'content-security-policy'])
            self.assertTrue(messages[1]['body'])

    async def test_unknown_or_traversal_asset_is_rejected(self):
        for name in ['../hosted.js','MANIFEST.json','unknown.js']:
            with self.assertRaises(playground.RequestError):
                await self.request('/static/super-resolution/'+name)
