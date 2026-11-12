#!/usr/bin/env python3
"""Outbound Kinex worker; browser visitors never receive robot capabilities."""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from remote_yam.cameras import CameraFrameSource
from remote_yam.controller import RunnerController
from remote_yam.kinex_policy import KinexAPI,KinexAdapter
from remote_yam.session import HttpSessionAPI
from remote_yam.kinex_safety import RoboHouseGuard,ROBOHOUSE,admission

API='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--site',required=True);parser.add_argument('--token-file',required=True)
    parser.add_argument('--upstream',required=True);parser.add_argument('--state',required=True);parser.add_argument('--preflight',required=True)
    parser.add_argument('--session-api',default=API);parser.add_argument('--model',default='gpt-6-astra');parser.add_argument('--robot-id',default=ROBOHOUSE);parser.add_argument('--execution-mode',choices=['interactive','automated_verification'],default='interactive');args=parser.parse_args()
    if not args.site.startswith('https://'):parser.error('A deployed HTTPS Site is required')
    from preflight import verify
    verify(args.preflight,args.upstream)
    token=Path(args.token_file).read_text().strip();state=Path(args.state);state.mkdir(parents=True,exist_ok=True)
    def call(path,data):
        req=Request(args.site+path,data=json.dumps(data,allow_nan=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token,'User-Agent':'Kinex-BluPe-Worker/1.0 (+https://github.com/andlyu/blupe-kinex)'})
        with urlopen(req,timeout=12) as response:return json.load(response)
    def heartbeat(ready=True,message='Kinex runner connected. Ready for bounded joint and gripper tasks.'):
        call('/api/runner/heartbeat',{'ready':ready,'message':message,'approach':'Kinex','underlying_model':args.model})
    controller=None;policy=None;job=None;api=None
    def retain_backend_evidence():
        if not api or not job or not api.session_id:return
        directory=state/job['id']/'evidence';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        for name,read in [('backend-session-final.json',lambda:api.get_session(api.session_id)),('backend-trace.json',lambda:api.get_episode_trace(api.session_id))]:
            try:
                path=directory/name;path.write_text(json.dumps(read(),indent=2,allow_nan=False)+'\n');path.chmod(0o600)
            except Exception as error:print('Evidence retention '+name+': '+type(error).__name__,flush=True)
    monitor=HttpSessionAPI(args.session_api,timeout_s=5,robot_id=args.robot_id)
    def readiness():
        try:
            result=monitor.get_robot_observation(args.robot_id);obs=result.get('observation') or result.get('payload') or result
            queue=monitor._request('GET','/v1/queue?robot_id='+args.robot_id)
            if args.robot_id==ROBOHOUSE:
                RoboHouseGuard().validate_report(monitor._request('GET','/v1/robots/'+args.robot_id+'/calibration'))
            return admission(queue,obs,args.robot_id)
        except Exception:return False,'Cannot verify fresh station connection, calibration and queue readiness. Restore the station before running.'
    try:
        while True:
            try:
                gate=verify(args.preflight,args.upstream);ready,reason=readiness()
                if ready and gate.get('physical_command_contract',{}).get(args.robot_id)!='verified':
                    ready=False;reason='Offline Kinex tool checks passed. Station safety/calibration verification is pending; hardware Run is disabled.'
                heartbeat(ready,reason)
                if not ready:time.sleep(3);continue
                job=call('/api/runner/claim',{}).get('run')
                if not job:time.sleep(.8);continue
                api=KinexAPI(HttpSessionAPI(args.session_api,supports_trajectories=True,robot_id=args.robot_id),job['name'],job['email'],robot_id=args.robot_id,private_state=state/job['id']/'evidence')
                policy=KinexAdapter(args.upstream,state/'workspace',api,CameraFrameSource(args.session_api),model=args.model,evidence_root=state/job['id']/'evidence',robot_id=args.robot_id)
                policy.runner_name=job['name'];policy.execution_mode=args.execution_mode
                controller=RunnerController(api,robot_id=args.robot_id,hardware_control_enabled=True,recording_root=state/'recordings')
                config=policy.public_config();config.pop('recording_path',None)
                call('/api/runner/update',dict(id=job['id'],status='preparing',stage='Joining BluPe queue',message='Requesting normal queue admission and robot readiness.',configuration=config))
                controller.join_and_run(policy,job['prompt'],run_duration_s=job['duration_s'])
                while True:
                    snapshot=controller.status();status=snapshot['status'];events=(snapshot.get('interactions') or {}).get('events',[])
                    config=policy.public_config();config.pop('recording_path',None)
                    clean=[{'time':e.get('timestamp',e.get('time',time.time())),'kind':e.get('kind'),'message':e.get('message','')[:6000]} for e in events[-60:]]
                    stage={'queued':'Waiting in robot queue','preparing':'Preparing robot','running':'Kinex running'}.get(status,status.replace('_',' ').title())
                    last=clean[-1]['message'] if clean else stage
                    if policy._finished_normally:stage='Kinex agent finished';last='Agent finished. Physical task outcome is unverified.'
                    terminal=status not in ('queued','preparing','running')
                    published='completed' if terminal and snapshot.get('error') is None and policy._finished_normally and any(e.get('kind')=='stop_requested' and e.get('details',{}).get('reason')=='policy_complete' for e in events) else status
                    if published not in ('completed','failed','stopped','timed_out','queued','preparing','running'):published='failed'
                    response=call('/api/runner/update',dict(id=job['id'],status='queued_robot' if published=='queued' else published,
                        stage=stage,message=last,configuration=config,episode_id=snapshot.get('episode_id'),session_id=snapshot.get('session_id'),
                        events=clean,metrics=snapshot.get('run_metrics',{}),error=snapshot.get('error')))
                    heartbeat(False,'Kinex is releasing the run and verifying cleanup.' if terminal else 'Kinex run in progress.')
                    if response.get('stop') and not terminal:controller.stop('user_requested');policy.request_stop()
                    if terminal:break
                    time.sleep(.5)
                policy.close_transport();retain_backend_evidence();controller=None;policy=None;job=None;api=None
            except Exception as error:
                print(type(error).__name__+': '+str(error),flush=True)
                if job:
                    import traceback
                    directory=state/job['id']/'evidence';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
                    with (directory/'worker-error.log').open('w') as stream:traceback.print_exc(file=stream)
                if controller:
                    try:controller.stop('runner_failed')
                    except Exception:pass
                cleanup_error=None
                if policy:
                    try:policy.close_transport()
                    except Exception as failure:cleanup_error=str(failure)
                retain_backend_evidence()
                if job:
                    try:call('/api/runner/update',dict(id=job['id'],status='failed',stage='Run stopped',message='Kinex could not complete this run. No automatic retry.',error=str(error)[:1000]))
                    except Exception:pass
                    job=None
                controller=None;policy=None;api=None
                if cleanup_error:
                    while True:
                        try:heartbeat(False,'Kinex cleanup failed: '+cleanup_error+'. Restore and verify the station before restarting the worker.')
                        except Exception:pass
                        time.sleep(3)
                time.sleep(2)
    finally:
        if controller:controller.stop('user_requested')
        if policy:policy.close_transport()

if __name__=='__main__':main()
