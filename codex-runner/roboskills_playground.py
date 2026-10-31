"""RoboSkills provider installed in the shared BluPe remote-arms harness."""
import argparse
import json
from pathlib import Path
from playground import HostedRunner, RequestError
from remote_yam.roboskills_policy import RoboSkillsPolicy, APPROACH
from remote_yam.api_depth_set import ApiDepthSet


class RoboSkillsPlayground(HostedRunner):
    def __init__(self, *, inference_model='gpt-6-sol', subsequent_inference_model='gpt-6-astra', **kwargs):
        self.inference_model=inference_model
        self.subsequent_inference_model=subsequent_inference_model
        self.perception_origin=kwargs['session_api']
        super().__init__(extra_providers={'roboskills':self.roboskills},
                         default_provider='roboskills',**kwargs)

    def roboskills(self,model,directory):
        if model not in ('',APPROACH):raise RequestError(400,'Choose RoboSkills')
        source=ApiDepthSet(self.perception_origin,self.perception_origin,robot_id=self.robot_id)
        report=json.loads(source.apis['top'].read('/calibration',256_000))
        policy=RoboSkillsPolicy(camera_source=source,recording_root=directory,
                               inference_model=self.inference_model,
                               subsequent_inference_model=self.subsequent_inference_model)
        policy.configure_perception(source,report)
        return policy

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
    p.add_argument('--inference-model',default='gpt-6-sol',help='Initial decision model (none reasoning)')
    p.add_argument('--subsequent-inference-model',default='gpt-6-astra',help='Later decision model (medium reasoning)')
    p.add_argument('--robot-id',default='yam-1')
    p.add_argument('--api',default='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com')
    p.add_argument('--recording-root',type=Path,required=True)
    a=p.parse_args()
    import uvicorn
    origin=f'http://127.0.0.1:{a.port}'
    app=RoboSkillsPlayground(inference_model=a.inference_model,subsequent_inference_model=a.subsequent_inference_model,
            public_origin=origin,session_api=a.api,camera_origin=a.api,
            robot_id=a.robot_id,recording_root=a.recording_root,hardware_control=True,
            development=True,share_conversation=True)
    print('RoboSkills BluPe harness: '+origin,flush=True)
    uvicorn.run(app,host='127.0.0.1',port=a.port,access_log=False)

if __name__=='__main__':main()
