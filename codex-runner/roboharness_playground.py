"""RoboHarness policy on the canonical BluPe queue, status, Stop and replay API.

Hosting owns the subscription executor and its existing IPC access; this shared
runner never reads or moves provider credentials.
"""
from contextlib import closing
import hashlib
import json
import re
import sqlite3
import threading
from pathlib import Path
from urllib.parse import parse_qs

from playground import HostedRunner,RequestError
from remote_yam.api_depth import ApiDepth
from remote_yam.roboharness_policy import RoboHarnessAdapter
from roboharness_preflight import source_inventory


def verify_release(receipt_path):
    receipt=json.loads(Path(receipt_path).read_text())
    root=Path(__file__).parent
    if receipt.get('status')!='passed' or receipt.get('tests_run',0)<70 or receipt.get('dirty_source') is not False:
        raise ValueError('A clean-source RoboHarness command-contract preflight is required')
    hashes=receipt.get('source_sha256',{})
    if set(hashes)!=set(source_inventory()):raise ValueError('Preflight source inventory is incomplete')
    for name,digest in hashes.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('RoboHarness preflight is stale: '+name)
    return receipt


class RoboHarnessPlayground(HostedRunner):
    def __init__(self,*,attach_model,model_status,calibration_config,preflight_receipt,
                 underlying_model='gpt-6-astra',public_replay_root=None,**kwargs):
        self.attach_model=attach_model;self.model_status=model_status
        self.calibration_config=calibration_config;self.preflight_receipt=preflight_receipt
        self.underlying_model=underlying_model
        self.camera_origin=kwargs['camera_origin']
        super().__init__(**kwargs,default_provider='roboharness')
        self.extra_providers={'roboharness':self.roboharness_provider}
        self.public_replays=None
        if public_replay_root is not None:
            from remote_yam.roboharness_replay import PublicCameraReplay
            from remote_yam.integration_runs import IntegrationRuns
            self.public_replays=PublicCameraReplay(public_replay_root,robot_id=self.robot_id,origin=self.camera_origin)
            threading.Thread(target=self.public_replays.recover_pending,daemon=True,
                name='roboharness-recording-recovery').start()
            self.past_runs=IntegrationRuns(self.past_runs,[dict(database=str(self.run_names.path),
                replay_root=str(self.public_replays.root),robot_id=self.robot_id)])

    def roboharness_provider(self,model,directory):
        if model!='RoboHarness':raise RequestError(400,'Model must identify the executed approach: RoboHarness')
        try:
            verify_release(self.preflight_receipt)
            if self.public_replays is not None and not self.public_replays.ready():raise ValueError('Public camera replay encoder unavailable')
            if not self.model_status().get('ready'):raise ValueError('The selected Codex subscription model is unavailable')
            report=json.loads(ApiDepth(self.camera_origin,robot_id=self.robot_id).read('/calibration',256000))
            config=self.calibration_config[self.robot_id]
            provider=RoboHarnessAdapter(self.camera_origin,self.robot_id,report,
                expected_calibration_id=config['calibration_id'],expected_model_calibration_id=config['model_calibration_id'],
                model=self.underlying_model,recording_root=directory,warm_model_session=True)
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
        if payload.get('grounding_camera','top') not in ('top','left','right'):
            raise RequestError(400,'Select overhead, left wrist or right wrist depth')

    def launch(self,visitor,payload,**kwargs):
        def context(provider):
            provider.select_grounding_camera(payload.get('grounding_camera','top'))
            provider.runner_name=payload['runner_name'].strip()
            provider.execution_mode=payload.get('execution_mode','interactive')
            return provider
        result=super().launch(visitor,payload,provider_transform=context,**kwargs)
        if self.public_replays is not None:
            try:self.public_replays.start(visitor.controller)
            except Exception as exc:
                visitor.controller._interactions.add('replay_failed','Public camera recording could not start; the accepted run remains active.',cause_type=type(exc).__name__)
        return result

    async def session_extension(self,cookies,visitor):
        data,headers=await super().session_extension(cookies,visitor)
        return {**data,'default_provider':'roboharness','configured_providers':{'roboharness':{
            'model':'RoboHarness','label':'RoboHarness','underlying_model':self.underlying_model,
            'help':'Visual keypoints, optical-flow tracking, calibrated depth and geometric tools. Run uses the normal BluPe queue; Stop cancels the run.'}}},headers

    async def public_extension(self,scope,receive,send,headers):
        if scope['method']=='GET' and scope['path']=='/api/roboharness/replay-evidence':
            episode=parse_qs(scope.get('query_string',b'').decode()).get('episode_id',[''])[0]
            result=None
            if self.public_replays is not None and re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',episode):
                from remote_yam.integration_runs import PublicRunSource
                source=PublicRunSource(self.run_names.path,self.public_replays.root,self.robot_id)
                if source.rows().get(episode,{}).get('model')=='RoboHarness' and source.clip(episode):
                    metadata=json.loads((self.public_replays.root/(episode+'.json')).read_text())
                    result={k:metadata[k] for k in ('episode_id','robot_id','capture_source','capture_partial') if k in metadata}
                    result['preview']={k:v for k,v in source.clip(episode).items() if k in ('video_url','video_sha256','video_duration_s','camera_order')}
                    result['frames']=[{k:f[k] for k in ('received_at','source_captured_at','actual_image','video_at','presentation_hold') if k in f} for f in metadata.get('frames',[])[:1220] if isinstance(f,dict)]
            await self.json(send,200 if result else 404,result or {'error':'No retained camera evidence is ready for this episode and station.'})
            return True
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
                                  'code_revision','duration_s','calibration_id','model_calibration_id','prompt_sha256','tool_geometry_reference','grounding_camera','depth_grounding_roles')
                            result={'episode_id':episode,'robot_id':self.robot_id,
                                    'configuration':{k:config[k] for k in keys if k in config}}
                except (sqlite3.Error,ValueError):pass
            await self.json(send,200 if result else 404,result or {'error':'No RoboHarness configuration is recorded for this episode and station.'})
            return True
        if scope['method']=='GET' and scope['path']=='/api/roboharness/readiness':
            try:
                receipt=verify_release(self.preflight_receipt);status=self.model_status()
                replay_ready=self.public_replays is None or self.public_replays.ready()
                await self.json(send,200,{'ready':status.get('ready') is True and replay_ready,'model':'RoboHarness',
                    'underlying_model':self.underlying_model,'reasoning_effort':'low',
                    'source_revision':receipt['source_revision'],'preflight_tests':receipt['tests_run'],
                    'grounding_cameras':['top','left','right'],
                    'retained_camera_capture':self.public_replays is not None,'replay_encoder_ready':replay_ready,
                    'reason':('Public camera replay encoder is unavailable. No run has been submitted.' if not replay_ready else None if status.get('ready') else 'The selected subscription model is unavailable. No run has been submitted.')})
            except Exception:
                await self.json(send,200,{'ready':False,'model':'RoboHarness','reason':'The release preflight is missing or stale. No run has been submitted.'})
            return True
        return await super().public_extension(scope,receive,send,headers)
