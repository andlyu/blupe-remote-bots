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
from replay import KinexReplay

API='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'

def progress(status,policy,events,queue_lifecycle=None):
    lifecycle=queue_lifecycle or {}
    if status=='queued':
        if lifecycle.get('admitted_at') is not None:
            return 'Preparing robot','Robot admission is confirmed. Waiting for fresh settled Home feedback before Kinex can start. Stop is available.'
        return 'Waiting for robot admission','Waiting for the normal robot session/lease grant. Station initialization may run while queued; it is not method motion. Stop is available.'
    stage={'queued':'Waiting in robot queue','preparing':'Preparing robot'}.get(status,status.replace('_',' ').title())
    last=events[-1].get('message',stage) if events else stage
    if status!='running':return stage,last
    if policy._active:return 'Executing Kinex motion','The gateway is executing the validated buffer. Waiting for measured completion before another command. Stop is available.'
    if policy._pending:return 'Validating Kinex motion','Checking fresh robot state and the command before dispatch. Waiting for gateway acknowledgement; no automatic retry.'
    if policy._thread is not None:return 'Astra is planning','Waiting for Astra to choose its next Kinex action. No new motion is being submitted during this wait. Stop is available.'
    return 'Checking robot feedback',last

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
        attempts=2 if path in ('/api/runner/update','/api/runner/heartbeat') else 1
        for attempt in range(attempts):
            try:
                with urlopen(req,timeout=3) as response:return json.load(response)
            except TimeoutError:
                if attempt+1==attempts:raise
                # Only status/heartbeat are idempotent. Never replay claims,
                # queue admission or actuator requests after an unknown outcome.
                print('Website status publication timed out; retrying status only.',flush=True)
                time.sleep(.1)
    def heartbeat(ready=True,message='Kinex runner connected. Ready for bounded joint and gripper tasks.',stage=None):
        call('/api/runner/heartbeat',{'ready':ready,'message':message,'approach':'Kinex','underlying_model':args.model,**({'stage':stage} if stage else {})})
    controller=None;policy=None;job=None;api=None;publication_sequence=0;replay=None;replay_thread=None
    def publish(data):
        nonlocal publication_sequence
        publication_sequence+=1
        return call('/api/runner/update',dict(data,publication_sequence=publication_sequence))
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
            return admission(queue,obs,args.robot_id,wait_for_clock=True)
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
                publication_sequence=0
                api=KinexAPI(HttpSessionAPI(args.session_api,supports_trajectories=True,robot_id=args.robot_id),job['name'],job['email'],robot_id=args.robot_id,private_state=state/job['id']/'evidence')
                policy=KinexAdapter(args.upstream,state/'workspace',api,CameraFrameSource(args.session_api),model=args.model,evidence_root=state/job['id']/'evidence',robot_id=args.robot_id)
                policy.runner_name=job['name'];policy.execution_mode=args.execution_mode
                controller=RunnerController(api,robot_id=args.robot_id,hardware_control_enabled=True,recording_root=state/'recordings')
                def upload_recording(meta,path,run_id=job['id']):
                    header={key:meta[key] for key in ('episode_id','session_id','robot_id','model','bytes','capture_partial','capture_fps','started_at','ended_at')}
                    header.update(sha256=meta['preview']['sha256'],duration_s=meta['preview']['duration_s'],
                        sample_count=len(meta['frames']),first_capture_at=meta['frames'][0]['received_at'],last_capture_at=meta['frames'][-1]['received_at'])
                    req=Request(args.site+'/api/runner/recordings/'+run_id,data=path.read_bytes(),headers={
                        'Authorization':'Bearer '+token,'Content-Type':'video/mp4','X-Kinex-Recording':json.dumps(header,allow_nan=False),
                        'User-Agent':'Kinex-BluPe-Worker/1.0 (+https://github.com/andlyu/blupe-kinex)'})
                    with urlopen(req,timeout=10) as response:return json.load(response)
                replay=KinexReplay(state/'camera-replays',robot_id=args.robot_id,upload=upload_recording)
                if not replay.ready():raise RuntimeError('Replay encoder is unavailable; install ffmpeg before running')
                config=policy.public_config();config.pop('recording_path',None)
                publish(dict(id=job['id'],status='preparing',stage='Joining BluPe queue',message='Requesting normal queue admission and robot readiness.',configuration=config))
                controller.join_and_run(policy,job['prompt'],run_duration_s=job['duration_s'])
                replay_thread=replay.start(controller)
                while True:
                    snapshot=controller.status();status=snapshot['status'];events=(snapshot.get('interactions') or {}).get('events',[])
                    if status in ('queued','preparing'):
                        try:api.refresh_queue_entry()
                        except Exception:pass  # Missing evidence stays unknown; never invent a timestamp.
                    queue_lifecycle=dict(api.queue_lifecycle)
                    if policy._startup_observed_at is not None:queue_lifecycle['home_observed_at']=policy._startup_observed_at
                    config=policy.public_config();config.pop('recording_path',None)
                    clean=[{'time':e.get('timestamp',e.get('time',time.time())),'kind':e.get('kind'),'message':e.get('message','')[:6000]} for e in events[-60:]]
                    stage,last=progress(status,policy,clean,queue_lifecycle)
                    if policy._finished_normally:stage='Kinex agent finished';last='Agent finished. Physical task outcome is unverified.'
                    terminal=status not in ('queued','preparing','running')
                    published='completed' if terminal and snapshot.get('error') is None and policy._finished_normally and any(e.get('kind')=='stop_requested' and e.get('details',{}).get('reason')=='policy_complete' for e in events) else status
                    if published not in ('completed','failed','stopped','timed_out','queued','preparing','running'):published='failed'
                    response=publish(dict(id=job['id'],status='queued_robot' if published=='queued' else published,
                        stage=stage,message=last,configuration=config,episode_id=snapshot.get('episode_id'),session_id=snapshot.get('session_id'),
                        events=clean,queue_lifecycle=queue_lifecycle,metrics=snapshot.get('run_metrics',{}),error=snapshot.get('error'),
                        **({'recording_capture':dict(state='processing',reason='The run has finished. Preparing its retained camera replay; no robot rerun is needed.')} if terminal else {})))
                    heartbeat(False,'Kinex is releasing the run and verifying cleanup.' if terminal else 'Kinex run in progress.')
                    if response.get('stop') and not terminal:controller.stop('user_requested');policy.request_stop()
                    if terminal:replay.allow_publish();break
                    time.sleep(.5)
                while replay_thread.is_alive():
                    heartbeat(False,'The run has finished. Preparing and retaining its timestamped camera playback. The robot is not being rerun.',stage='Preparing replay')
                    replay_thread.join(.5)
                if replay.phase=='failed':
                    publish(dict(id=job['id'],status=published,recording_capture=dict(state='failed',
                        reason='The immediate camera recording could not be retained. The normal BluPe archive is being checked; the robot will not be rerun.')))
                policy.close_transport();retain_backend_evidence();controller=None;policy=None;job=None;api=None;replay=None;replay_thread=None
            except Exception as error:
                print(type(error).__name__+': '+str(error),flush=True)
                if job:
                    import traceback
                    directory=state/job['id']/'evidence';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
                    with (directory/'worker-error.log').open('w') as stream:traceback.print_exc(file=stream)
                if controller:
                    try:controller.stop('runner_failed')
                    except Exception:pass
                if replay:replay.close()
                cleanup_error=None
                if policy:
                    try:policy.close_transport()
                    except Exception as failure:cleanup_error=str(failure)
                retain_backend_evidence()
                if job:
                    try:publish(dict(id=job['id'],status='failed',stage='Run stopped',message='Kinex could not complete this run. No automatic retry.',error=str(error)[:1000]))
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
        if replay:replay.close()
        if policy:policy.close_transport()

if __name__=='__main__':main()
