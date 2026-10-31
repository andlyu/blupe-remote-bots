"""RoboSkills provider installed in the shared BluPe remote-arms harness."""
import argparse
from pathlib import Path
from playground import HostedRunner, RequestError
from remote_yam.roboskills_policy import RoboSkillsPolicy, APPROACH


class RoboSkillsPlayground(HostedRunner):
    def __init__(self, *, inference_model='gpt-6-sol', **kwargs):
        self.inference_model=inference_model
        super().__init__(extra_providers={'roboskills':self.roboskills},
                         default_provider='roboskills',**kwargs)

    def roboskills(self,model,directory):
        if model not in ('',APPROACH):raise RequestError(400,'Choose RoboSkills')
        return RoboSkillsPolicy(camera_source=self.camera_source,recording_root=directory,
                               inference_model=self.inference_model)

    async def session_extension(self,cookies,visitor):
        return {'configured_providers':{'roboskills':dict(label='RoboSkills · Python agent',
                model=APPROACH,help='Upstream persistent Python agent, executing through BluPe remote arms.')}},[]

    def validate_launch(self,visitor,payload,paid):
        if payload.get('provider')!='roboskills':raise RequestError(400,'This runner executes RoboSkills')
        if not payload.get('runner_name') or not payload.get('email'):
            raise RequestError(400,'Confirm your name and email before joining')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8797)
    p.add_argument('--inference-model',default='gpt-6-sol')
    p.add_argument('--robot-id',default='yam-1')
    p.add_argument('--api',default='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com')
    p.add_argument('--recording-root',type=Path,required=True)
    a=p.parse_args()
    import uvicorn
    origin=f'http://127.0.0.1:{a.port}'
    app=RoboSkillsPlayground(inference_model=a.inference_model,public_origin=origin,session_api=a.api,camera_origin=a.api,
            robot_id=a.robot_id,recording_root=a.recording_root,hardware_control=True,
            development=True,share_conversation=True)
    print('RoboSkills BluPe harness: '+origin,flush=True)
    uvicorn.run(app,host='127.0.0.1',port=a.port,access_log=False)

if __name__=='__main__':main()
