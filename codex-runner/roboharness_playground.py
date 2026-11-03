"""RoboHarness policy on the canonical BluPe queue, status, Stop and replay API.

Hosting owns the subscription executor and its existing IPC access; this shared
runner never reads or moves provider credentials.
"""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs

from playground import HostedRunner,RequestError
from remote_yam.api_depth import ApiDepth
from remote_yam.roboharness_policy import RoboHarnessAdapter
from roboharness_preflight import source_inventory


def verify_release(receipt_path):
    receipt=json.loads(Path(receipt_path).read_text())
    root=Path(__file__).parent
    if receipt.get('status')!='passed' or receipt.get('tests_run',0)<35 or receipt.get('dirty_source') is not False:
        raise ValueError('A clean-source RoboHarness command-contract preflight is required')
    hashes=receipt.get('source_sha256',{})
    if set(hashes)!=set(source_inventory()):raise ValueError('Preflight source inventory is incomplete')
    for name,digest in hashes.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('RoboHarness preflight is stale: '+name)
    return receipt


class RoboHarnessPlayground(HostedRunner):
    def __init__(self,*,attach_model,model_status,calibration_config,preflight_receipt,
                 underlying_model='gpt-6-astra',**kwargs):
        self.attach_model=attach_model;self.model_status=model_status
        self.calibration_config=calibration_config;self.preflight_receipt=preflight_receipt
        self.underlying_model=underlying_model
        self.camera_origin=kwargs['camera_origin']
        super().__init__(**kwargs,default_provider='roboharness')
        self.extra_providers={'roboharness':self.roboharness_provider}

    def roboharness_provider(self,model,directory):
        if model!='RoboHarness':raise RequestError(400,'Model must identify the executed approach: RoboHarness')
        try:
            verify_release(self.preflight_receipt)
            if not self.model_status().get('ready'):raise ValueError('The selected Codex subscription model is unavailable')
            report=json.loads(ApiDepth(self.camera_origin,robot_id=self.robot_id).read('/calibration',256000))
            config=self.calibration_config[self.robot_id]
            provider=RoboHarnessAdapter(self.camera_origin,self.robot_id,report,
                expected_calibration_id=config['calibration_id'],expected_model_calibration_id=config['model_calibration_id'],
                model=self.underlying_model,recording_root=directory)
            return self.attach_model(provider)
        except (ValueError,RuntimeError,OSError,KeyError) as exc:
            raise RequestError(503,'RoboHarness is not ready: '+str(exc)) from None

    def validate_launch(self,visitor,payload,paid):
        super().validate_launch(visitor,payload,paid)
        if payload.get('provider')!='roboharness' or payload.get('model')!='RoboHarness':
            raise RequestError(400,'This integration runs RoboHarness only')
        name=payload.get('runner_name');email=payload.get('email')
        if not isinstance(name,str) or not name.strip() or name.strip().lower() in ('anonymous','automated','autonomous'):
            raise RequestError(400,'Confirm the actual runner name before joining')
        if not isinstance(email,str) or not email.strip() or len(email)>200 or '@' not in email or any(c.isspace() for c in email):
            raise RequestError(400,'Confirm a valid runner email before joining')
        if any(payload.get(k) for k in ('api_key','endpoint','executor','system_prompt','system_prompt_text','system_prompt_preset')):
            raise RequestError(400,'Use the configured RoboHarness model and geometric tools')
        if payload.get('execution_mode','interactive') not in ('interactive','automated_verification'):
            raise RequestError(400,'Choose an explicit supported execution mode')

    def launch(self,visitor,payload,**kwargs):
        def context(provider):
            provider.runner_name=payload['runner_name'].strip()
            provider.execution_mode=payload.get('execution_mode','interactive')
            return provider
        return super().launch(visitor,payload,provider_transform=context,**kwargs)

    async def session_extension(self,cookies,visitor):
        data,headers=await super().session_extension(cookies,visitor)
        return {**data,'default_provider':'roboharness','configured_providers':{'roboharness':{
            'model':'RoboHarness','label':'RoboHarness','underlying_model':self.underlying_model,
            'help':'Visual keypoints, optical-flow tracking, calibrated depth and geometric tools. Run uses the normal BluPe queue; Stop cancels the run.'}}},headers

    async def public_extension(self,scope,receive,send,headers):
        if scope['method']=='GET' and scope['path']=='/api/roboharness/run-config':
            episode=parse_qs(scope.get('query_string',b'').decode()).get('episode_id',[''])[0]
            result=None
            if re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',episode) and self.run_names.path.exists():
                try:
                    with closing(sqlite3.connect(self.run_names.path)) as db:
                        row=db.execute('SELECT c.configuration FROM run_configuration c JOIN run_metadata m USING(episode_id) WHERE episode_id=? AND m.robot_id=?',(episode,self.robot_id)).fetchone()
                    if row:
                        config=json.loads(row[0])
                        if config.get('model')=='RoboHarness':
                            keys=('model','provider','underlying_models','runner_name','execution_mode','reasoning',
                                  'code_revision','duration_s','calibration_id','model_calibration_id','prompt_sha256')
                            result={'episode_id':episode,'robot_id':self.robot_id,
                                    'configuration':{k:config[k] for k in keys if k in config}}
                except (sqlite3.Error,ValueError):pass
            await self.json(send,200 if result else 404,result or {'error':'No RoboHarness configuration is recorded for this episode and station.'})
            return True
        if scope['method']=='GET' and scope['path']=='/api/roboharness/readiness':
            try:
                receipt=verify_release(self.preflight_receipt);status=self.model_status()
                await self.json(send,200,{'ready':status.get('ready') is True,'model':'RoboHarness',
                    'underlying_model':self.underlying_model,'reasoning_effort':'low',
                    'source_revision':receipt['source_revision'],'preflight_tests':receipt['tests_run'],
                    'reason':None if status.get('ready') else 'The selected subscription model is unavailable. No run has been submitted.'})
            except Exception:
                await self.json(send,200,{'ready':False,'model':'RoboHarness','reason':'The release preflight is missing or stale. No run has been submitted.'})
            return True
        return await super().public_extension(scope,receive,send,headers)
