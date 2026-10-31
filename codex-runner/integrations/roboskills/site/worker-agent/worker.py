"""Poll the Site's authenticated worker API; retain genuine upstream simulation outputs.

Configuration is a single JSON object on stdin. Secrets remain in process memory.
No robot control is present in this worker.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from urllib.parse import urlencode, urlsplit
import urllib.request

REVISION='8a2860234768b4bec981994d1c14fa380a2c8c7f'

def read_config():
    if not sys.stdin.isatty():
        return json.loads(sys.stdin.readline())
    import termios
    flags=termios.tcgetattr(sys.stdin.fileno());hidden=flags.copy();hidden[3]&=~termios.ECHO
    termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,hidden)
    print('Ready for worker configuration on stdin (input hidden).',flush=True)
    try:return json.loads(sys.stdin.readline())
    finally:termios.tcsetattr(sys.stdin.fileno(),termios.TCSANOW,flags)

class Worker:
    def __init__(self, config):
        self.config=config
        self.origin=config['origin'].rstrip('/')
        u=urlsplit(self.origin)
        if u.scheme!='https' and not(u.scheme=='http' and u.hostname in ('localhost','127.0.0.1')):
            raise ValueError('Use a trusted HTTPS Site or a loopback preview.')
        self.id=uuid.uuid4().hex
        self.python=os.path.abspath(config['python'])
        self.root=Path(config['runs']).resolve();self.root.mkdir(parents=True,exist_ok=True)
        self.child=None

    def request(self, action, body=None, *, binary=None, name=None, run=None):
        headers={'Authorization':'Bearer '+self.config['workerToken'],'X-Worker-Id':self.id,
                 'User-Agent':'BluPe-RoboSkills-Worker/1.0'}
        if binary is None:
            headers['Content-Type']='application/json';data=json.dumps({'worker':self.id,**(body or {})}).encode()
        else:
            data=binary;headers['Content-Type']='application/octet-stream';action+='?'+urlencode({'id':run,'name':name})
        with urllib.request.urlopen(urllib.request.Request(self.origin+self.config.get('apiPath','/api/worker/')+action,data=data,headers=headers),timeout=40) as response:
            return json.load(response)

    def update(self,run,status,stage,result=None):
        self.request('update',dict(id=run['id'],status=status,stage=stage,**({'result':result} if result else {})))

    def heartbeat(self,run=None,detail='Ready to build and solve a new bimanual scene.'):
        return self.request('heartbeat',dict(run=run,detail=detail))

    def terminate(self):
        if not self.child or self.child.poll() is not None:
            return
        # Upstream launches independent process groups for model and shell calls.
        # Collect only descendants of our retained PID so Stop reaches those too.
        rows=subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines()
        pairs=[tuple(map(int,line.split())) for line in rows if len(line.split())==2]
        owned={self.child.pid}
        for _ in range(len(pairs)):
            extra={pid for pid,parent in pairs if parent in owned}-owned
            if not extra:break
            owned.update(extra)
        for sig in (signal.SIGTERM,signal.SIGKILL):
            for pid in sorted(owned,reverse=True):
                try:os.kill(pid,sig)
                except ProcessLookupError:pass
            if sig==signal.SIGTERM:
                try:self.child.wait(timeout=3)
                except subprocess.TimeoutExpired:pass
        self.child.wait()

    def upload(self,run,folder):
        outputs={}
        for phase,filename in [('build','demo.mp4'),('solve','solve.mp4')]:
            directory=folder/phase
            result=directory/'result.json'
            if result.exists():
                outputs[phase+'.json']=result
                j=json.loads(result.read_text())
                checks=sorted(directory.glob('round-*/check'),key=lambda p:int(p.parent.name.split('-')[1]))
                check=directory/j['check'] if j.get('check') else (checks[-1] if checks else None)
                if check and (check/'receipt.json').is_file():outputs[phase+'.json']=check/'receipt.json'
                if check and (check/filename).is_file():outputs[phase+'.mp4']=check/filename
        for name,path in [('task.py',folder/'build/work/task.py'),('solution.py',folder/'solve/work/solution.py'),('notes.md',folder/'solve/work/notes.md')]:
            if path.is_file():outputs[name]=path
        for name,path in outputs.items():
            if path.stat().st_size>32*1024*1024:
                if not name.endswith('.mp4'):raise RuntimeError('Output exceeds storage limit: '+name)
                compressed=folder/(name.replace('.mp4','-web.mp4'))
                subprocess.run(['ffmpeg','-y','-i',str(path),'-vf','scale=960:-2','-c:v','libx264','-crf','28','-movflags','+faststart','-an',str(compressed)],check=True,capture_output=True)
                path=compressed
            self.request('upload',binary=path.read_bytes(),name=name,run=run['id'])

    def execute(self,run):
        folder=self.root/run['id'];request=self.root/(run['id']+'-request.json')
        request.write_text(json.dumps(run))
        command=[self.python,str(Path(__file__).with_name('execute.py')),'--request',str(request),'--out',str(folder),'--python',self.python,'--model',self.config.get('model','gpt-6-astra'),'--hours',str(self.config.get('hours',1))]
        with (self.root/(run['id']+'.log')).open('w') as log:
            self.child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            phase='building'
            try:
                while self.child.poll() is None:
                    beat=self.heartbeat(run['id'],'Running a bimanual simulation. Other tasks wait for this worker.')
                    if beat.get('cancel'):
                        self.terminate();self.update(run,'cancelled','Stopped by the runner. This simulation was not retried.');return
                    if (folder/'phase.json').exists() and phase!='solving':
                        phase='solving';self.update(run,'solving','Task built and frozen. A fresh agent is writing and checking its solution across eight seeds.')
                    time.sleep(4)
                path=folder/'result.json'
                result=json.loads(path.read_text()) if path.exists() else {'passed':False,'error':'The upstream process ended without a result. See the worker log.'}
                result['provenance']={'upstream':REVISION,'workflow':'agentic_sim','model':self.config.get('model','gpt-6-astra'),'simulators':'MuJoCo and Blender available; native task records the selected simulator','robot':'bimanual YAM requested','execution':'simulation'}
                self.update(run,'uploading','Execution ended. Saving native checks, code and available simulation replays.')
                self.upload(run,folder)
                passed=bool(result.get('passed'))
                stage='All eight solver seeds passed the native checks.' if passed else ('The model request failed before a scene was built. Review the saved error, then start a new run.' if result.get('build',{}).get('error') and not result.get('build',{}).get('rounds') else 'The native workflow did not pass. Review its saved results and generated code.')
                self.update(run,'passed' if passed else 'failed',stage,result)
            except BaseException:
                self.terminate();raise
            finally:self.child=None

    def serve(self):
        # A real import plus pinned source check is required before advertising ready.
        import roboskills
        repository=Path(roboskills.__file__).resolve().parents[2]
        revision=subprocess.check_output(['git','-C',str(repository),'rev-parse','HEAD'],text=True,timeout=15).strip()
        if revision!=REVISION:raise RuntimeError('Unexpected RoboSkills revision')
        subprocess.run([self.python,'-c','import mujoco,bpy,robokit; import robokit.assets.robots.arms.yam'],check=True)
        try:
            while True:
                try:
                    self.heartbeat()
                    run=self.request('claim').get('run')
                except Exception as error:
                    print('Connection unavailable: '+type(error).__name__+'. Reconnecting in four seconds.',flush=True)
                    time.sleep(4)
                    continue
                if run:
                    try:self.execute(run)
                    except Exception as error:
                        self.update(run,'failed','Worker error: '+str(error)[:500],{'passed':False,'error':str(error)[:2000]})
                else:time.sleep(4)
        finally:self.terminate()

if __name__=='__main__':
    config=read_config()
    # Keep model assets and new generated outputs within the requested workspace.
    os.environ['HF_HOME']=str(Path(config['runs']).resolve().parent/'hf-cache')
    Worker(config).serve()
