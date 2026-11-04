"""Normal local BluPe playground configured for the reviewed minute capture."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.request import urlopen

from local_playground import LocalPlayground
from playground import RequestError
from minute_policy import MinutePolicy,METHOD,TASK

HERE=Path(__file__).parent
SOURCE_FILES=('minute_policy.py','viewpoint_sim.py','scene_video.py')

class MinutePlayground(LocalPlayground):
    def __init__(self,args):
        self.args=args
        super().__init__(public_origin=f'http://127.0.0.1:{args.port}',session_api=args.api,
            camera_origin=args.api,robot_id='yam-1',hardware='yam',development=True,
            hardware_control=True,share_conversation=True,default_provider='scene_video_minute',
            recording_root=args.output/'runs',visitor_chat_origin=None)
        self.cookie_name+='-scene-minute'
        self.extra_providers['scene_video_minute']=self.make_minute
        self.visitor_chat_origin=None

    def make_minute(self,model,directory):
        if model!=METHOD:raise RequestError(400,'Select the one-minute scene capture')
        receipt=json.loads((self.args.simulation/'verification.json').read_text())
        if (receipt.get('status')!='PASS' or receipt.get('duration_s')!=60
                or not receipt.get('minute_regressions_passed')):
            raise RequestError(409,'Run the full minute capture preflight')
        for name in SOURCE_FILES:
            if receipt.get('launch_source_sha256',{}).get(name)!=hashlib.sha256((HERE/name).read_bytes()).hexdigest():
                raise RequestError(409,'Motion source changed; repeat the minute preflight')
        report=json.loads(urlopen(self.args.api+'/v1/robots/yam-1/calibration',timeout=15).read())
        if report['calibration_id']!=receipt['calibration_id']:
            raise RequestError(409,'Camera calibration changed; repeat simulation')
        return MinutePolicy(report,directory,hardware_root=self.args.hardware_root)

    async def session_extension(self,cookies,visitor):
        metadata,headers=await super().session_extension(cookies,visitor)
        return {**metadata,'local_runner':True,'default_provider':'scene_video_minute',
            'configured_providers':{'scene_video_minute':dict(label=METHOD,model=METHOD,task=TASK,
                default_run_duration_s=120,help='60 seconds of camera motion: raise, advance and scan '
                'right, advance and scan left, then cover near/far scene regions. Both grippers hold. '
                'Normal queue, Home, Stop and dataset capture apply. Session allowance: 120 seconds.')}},headers

    def validate_launch(self,visitor,payload,paid):
        if payload.get('provider')!='scene_video_minute' or payload.get('prompt','').strip()!=TASK:
            raise RequestError(400,'This playground runs the verified one-minute scene capture')
        if payload.get('run_duration_s',120)!=120:
            raise RequestError(400,'Use the 120-second session allowance for the 60-second path')
        if payload.get('runner_name','').strip().lower() in ('','anonymous','automated','autonomous'):
            raise RequestError(400,'Enter the confirmed human runner name')

    def page(self):
        page=super().page().decode()
        page=re.sub(r'(<textarea\b[^>]*\bid="prompt"[^>]*>).*?(</textarea>)',
            lambda m:m[1]+html.escape(TASK)+m[2],page,flags=re.S)
        if self.args.identity_file:
            identity=json.loads(self.args.identity_file.read_text())
            for field,key in [('runnerName','name'),('email','email')]:
                value=html.escape(identity[key],quote=True)
                page=re.sub(r'(<input\b[^>]*\bid="'+field+r'"[^>]*)(>)',
                    lambda m:re.sub(r'\svalue="[^"]*"','',m[1])+' value="'+value+'"'+m[2],page)
        page=page.replace('</body>','<section style="padding:24px;max-width:1200px;margin:auto">'
            '<h2>Verified simulation · one-minute scene capture</h2><p>Simulation only: '
            'left wrist, overview, right wrist. 60 seconds of forward and sideways camera motion, '
            'aimed across the shared scene. Physical footage is saved in the matching dataset episode.</p>'
            '<video controls preload="metadata" style="width:100%" src="/scene-simulation.mp4"></video>'
            '</section></body>')
        return page.encode()

    async def http(self,scope,receive,send):
        if scope['method']=='GET' and scope['path']=='/scene-simulation.mp4':
            body=(self.args.simulation/'viewpoint-simulation.mp4').read_bytes()
            await send(dict(type='http.response.start',status=200,
                headers=[(b'content-type',b'video/mp4'),(b'content-length',str(len(body)).encode())]))
            await send(dict(type='http.response.body',body=body));return
        await super().http(scope,receive,send)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api',default='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com')
    parser.add_argument('--simulation',type=Path,required=True)
    parser.add_argument('--hardware-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--identity-file',type=Path)
    parser.add_argument('--port',type=int,default=8797)
    args=parser.parse_args()
    for name in ['simulation','hardware_root','output']:
        setattr(args,name,getattr(args,name).resolve())
    import uvicorn
    uvicorn.run(MinutePlayground(args),host='127.0.0.1',port=args.port,access_log=False)

if __name__=='__main__':main()
