"""Scene-video configuration of the existing physical BluPe playground."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.request import urlopen

from local_playground import LocalPlayground
from playground import RequestError
from scene_video import SweepPolicy, TASK, METHOD


class SceneVideoPlayground(LocalPlayground):
    def __init__(self, args):
        self.args = args
        super().__init__(public_origin=f'http://127.0.0.1:{args.port}', session_api=args.api,
            camera_origin=args.api, robot_id='yam-1', hardware='yam', development=True,
            hardware_control=True, share_conversation=True, default_provider='scene_video',
            recording_root=args.output/'runs', visitor_chat_origin=None)
        self.cookie_name += '-scene-video'
        self.extra_providers['scene_video'] = self.make_sweep
        # Chat is unrelated to this capture task; no chat messages are sent.
        self.visitor_chat_origin = None

    def make_sweep(self, model, directory):
        if model != METHOD:
            raise RequestError(400, 'Select Forward scene video')
        report = json.loads(urlopen(self.args.api+'/v1/robots/yam-1/calibration', timeout=15).read())
        if report['calibration_id'] != self.args.calibration_id:
            raise RequestError(409, 'Calibration changed; repeat the simulation preflight')
        receipt = json.loads((self.args.simulation/'verification.json').read_text())
        if receipt.get('status') != 'PASS':
            raise RequestError(409, 'Simulation verification has not passed')
        source_sha = hashlib.sha256(Path(__file__).with_name('scene_video.py').read_bytes()).hexdigest()
        if receipt.get('policy_sha256') != source_sha:
            raise RequestError(409, 'Sweep source changed; repeat the simulation preflight')
        verifier_sha=hashlib.sha256(Path(__file__).with_name('verify_sim.py').read_bytes()).hexdigest()
        if (receipt.get('verification_script_sha256') != verifier_sha
                or receipt.get('completion_regressions_passed') is not True):
            raise RequestError(409, 'Run the complete offline release preflight')
        return SweepPolicy(report, directory)

    async def session_extension(self, cookies, visitor):
        metadata, headers = await super().session_extension(cookies, visitor)
        return {**metadata, 'local_runner':True, 'default_provider':'scene_video',
            'configured_providers':{'scene_video':dict(label=METHOD, model=METHOD, task=TASK,
                default_run_duration_s=60, help='Both arms move forward 12 cm over 12 seconds, '
                'holding camera attitude and grippers. No model calls. Normal queue, Home, '
                'hardware validation, Stop, dataset recording and release apply.')}}, headers

    def validate_launch(self, visitor, payload, paid):
        if payload.get('provider') != 'scene_video' or payload.get('prompt','').strip() != TASK:
            raise RequestError(400, 'This playground runs only the verified scene-video sweep')
        if payload.get('run_duration_s',60) != 60:
            raise RequestError(400, 'This verified capture uses a 60-second maximum session')
        if payload.get('runner_name','').strip().lower() in ('', 'anonymous', 'automated', 'autonomous'):
            raise RequestError(400, 'Enter the confirmed human runner name')

    def page(self):
        page = super().page().decode()
        page = re.sub(r'(<textarea\b[^>]*\bid="prompt"[^>]*>).*?(</textarea>)',
                      lambda m:m[1]+html.escape(TASK)+m[2], page, flags=re.S)
        page = page.replace('</body>', '<section style="padding:24px;max-width:1200px;margin:auto">'
            '<h2>Verified simulation · forward scene video</h2><p>Simulation only: '
            'both arms advance 12 cm in 12 seconds. Wrist cameras stay directed over the scene. '
            'The physical recording is retained separately in the matching dataset episode.</p>'
            '<video controls preload="metadata" style="width:100%" src="/scene-simulation.mp4"></video>'
            '</section></body>')
        return page.encode()

    async def http(self, scope, receive, send):
        if scope['method']=='GET' and scope['path']=='/scene-simulation.mp4':
            body=(self.args.simulation/'simulation.mp4').read_bytes()
            await send(dict(type='http.response.start',status=200,
                headers=[(b'content-type',b'video/mp4'),(b'content-length',str(len(body)).encode())]))
            await send(dict(type='http.response.body',body=body))
            return
        await super().http(scope,receive,send)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api', default='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com')
    parser.add_argument('--calibration-id', required=True)
    parser.add_argument('--simulation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8796)
    args=parser.parse_args()
    args.simulation=args.simulation.resolve();args.output=args.output.resolve()
    import uvicorn
    uvicorn.run(SceneVideoPlayground(args), host='127.0.0.1', port=args.port, access_log=False)

if __name__=='__main__':main()
