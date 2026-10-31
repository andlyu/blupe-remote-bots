"""Site jobs -> configured RoboSkills provider in blupe-remote-arms.

No raw robot commands here: RunnerPolicyClient uses the shared runner's normal
visitor/CSRF, Run, status and Stop. The controller owns the robot capability.
"""
import io
import json
from pathlib import Path
import threading
import time
import urllib.request

from remote_yam.runner_policy_client import RunnerPolicyClient
from worker import Worker,read_config
from physical_progress import lifecycle_events,admission_event,current_stage,task_outcome

API='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'


class PhysicalWorker(Worker):
    def __init__(self,config):
        super().__init__({**config,'apiPath':'/api/physical/worker/'})

    def request(self,action,body=None,**kwargs):
        # The physical route binds this identity before parsing job data.
        if kwargs.get('binary') is not None:
            return super().request(action,body,**kwargs)
        return self._json(action,body or {})

    def _json(self,action,body):
        headers={'Authorization':'Bearer '+self.config['workerToken'],
                 'X-Worker-Id':self.id,'Content-Type':'application/json',
                 'User-Agent':'BluPe-RoboSkills-Worker/1.0'}
        data=json.dumps(body).encode()
        with urllib.request.urlopen(urllib.request.Request(self.origin+'/api/physical/worker/'+action,
                data=data,headers=headers),timeout=15) as r:return json.load(r)

    def record(self,stop,folder):
        # Actual top-camera footage, retained independently of archive upload.
        from PIL import Image
        import imageio.v2 as imageio
        with imageio.get_writer(folder/'physical.mp4',fps=2,codec='libx264',
                                output_params=['-movflags','+faststart']) as video:
            while not stop.is_set():
                start=time.monotonic()
                try:
                    with urllib.request.urlopen(API+'/v1/robots/yam-1/cameras/top.jpg',timeout=3) as r:
                        image=Image.open(io.BytesIO(r.read())).convert('RGB')
                    video.append_data(__import__('numpy').asarray(image))
                except Exception:pass
                stop.wait(max(0,.5-(time.monotonic()-start)))

    def execute(self,run):
        folder=self.root/run['id'];folder.mkdir(exist_ok=False)
        client=RunnerPolicyClient(self.config['harness'],robot_id='yam-1',timeout=20)
        stop_record=threading.Event();recorder=None;state=None;stopped=False
        progress=[]
        seen_lifecycle=set()
        def advance(key,label,detail,at=None):
            if progress and progress[-1]['key']==key:return
            now=time.time()*1000 if at is None else at
            if progress:progress[-1]['completedAt']=now
            progress.append(dict(key=key,label=label,detail=detail,startedAt=now))
        try:
            client.connect()
            # Once only. A timeout is uncertain, never an automatic relaunch.
            client.start('roboskills',runner_name=run['runnerName'],email=run['runnerEmail'],
                         prompt=run['instruction'],run_duration_s=60)
            client.save(folder/'runner-session.json')
            recorder=threading.Thread(target=self.record,args=(stop_record,folder),daemon=True);recorder.start()
            previous=None
            while True:
                beat=self.request('heartbeat',dict(id=run['id'],detail='RoboSkills is connected through the BluPe remote-arms harness.'))
                state=client.status()
                result={key:state.get(key) for key in ('status','attempt_id','session_id','episode_id','error','commands_submitted','packets_submitted','run_started_at','run_ended_at','provider','step_timings','run_metrics','safety_error','run_summary')}
                result.update(approach='RoboSkills',execution='physical',robot_id='yam-1',inference_model=(state.get('provider') or {}).get('inference_model'))
                if isinstance(result.get('provider'),dict):
                    result['provider']=dict(result['provider'])
                    result['provider'].pop('recording_path',None)
                # Provider configuration is safe public metadata; no visitor or
                # session capabilities are included by this explicit projection.
                if beat.get('cancel') and not stopped:
                    client.stop();stopped=True
                status=state['status']
                lifecycle=lifecycle_events(state)
                result['lifecycle']=lifecycle
                # Durable observed queue/admission transitions survive fast polling.
                # Event receipt times are labelled as observed; not visual timing proof.
                for event in lifecycle:
                    if event.get('id') in seen_lifecycle:continue
                    seen_lifecycle.add(event.get('id'))
                    at=event.get('timestamp')
                    at=at*1000 if isinstance(at,(int,float)) else None
                    if event.get('kind')=='joined':
                        advance('queue','Waiting for robot admission','Queue entry observed by the BluPe runner.',at)
                    elif event==admission_event(lifecycle):
                        advance('preparing','Preparing the arms','Admission observed. BluPe is checking startup Home and readiness.',at)
                key,label,stage=current_stage(state,stopped)
                phase='running' if status=='running' else 'preparing'
                if status in ('queued','preparing','running'):advance(key,label,stage)
                result['progress']=list(progress)
                self.request('update',dict(id=run['id'],status=phase,stage=stage,result=result));previous=(status,stage)
                if status not in ('queued','preparing','running'):break
                time.sleep(1)
            advance('recording','Saving the replay','Physical run ended. Retaining actual YAM camera footage.')
            result['progress']=list(progress)
            self.request('update',dict(id=run['id'],status='recording',stage='Physical run ended. Saving actual YAM camera footage.',result=result))
            stop_record.set()
            if recorder:recorder.join(timeout=5)
            path=folder/'physical.mp4'
            if path.is_file() and path.stat().st_size>1000:
                self.request('upload',binary=path.read_bytes(),name='physical.mp4',run=run['id'])
            if progress:progress[-1]['completedAt']=time.time()*1000
            result['progress']=list(progress)
            result['taskOutcome']=task_outcome(state,stopped)
            (folder/'result.json').write_text(json.dumps(result,indent=2))
            self.request('upload',binary=(folder/'result.json').read_bytes(),name='result.json',run=run['id'])
            final=result['taskOutcome']
            self.request('update',dict(id=run['id'],status=final['status'],
                                      stage=final['label']+'. '+final['reason'],result=result))
        except Exception as exc:
            # Reconcile the same visitor and attempt. Never create a second run
            # after a contact failure; best-effort Stop is this owned run only.
            if client.attempt_id:
                try:client.stop()
                except Exception:pass
            stop_record.set()
            if recorder:recorder.join(timeout=5)
            result={'error':str(exc)[:1500],'approach':'RoboSkills','execution':'physical'}
            try:
                path=folder/'physical.mp4'
                if path.is_file() and path.stat().st_size>1000:
                    self.request('upload',binary=path.read_bytes(),name='physical.mp4',run=run['id'])
            except Exception as upload:result['recording_error']=type(upload).__name__
            self.request('update',dict(id=run['id'],status='failed',stage='BluPe contact or execution failed. This run was not retried. Review its retained camera footage.',result=result))
        finally:
            stop_record.set()
            if recorder:recorder.join(timeout=5)

    def serve(self):
        while True:
            try:
                self.request('heartbeat',{'detail':'RoboSkills connected through the BluPe remote-arms harness.'})
                run=self.request('claim',{}).get('run')
                if run:self.execute(run)
            except Exception as exc:print('Physical bridge contact issue: '+type(exc).__name__,flush=True)
            time.sleep(1)

if __name__=='__main__':
    PhysicalWorker(read_config()).serve()
