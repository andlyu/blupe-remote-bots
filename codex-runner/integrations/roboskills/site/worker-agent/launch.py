"""Detach the configured workers from the launching terminal. No job is replayed.

Read secrets once from hidden stdin; persist only PIDs and log paths. This is a
local service launcher, not a restart supervisor. An offline service needs an
explicit new launch. Existing live PIDs/occupied provider ports are never killed.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from worker import read_config


def running(pid):
    try:os.kill(int(pid),0)
    except (ProcessLookupError,ValueError):return False
    return True


def launch_process(command,config,*,log,env=None):
    with Path(log).open('ab') as output:
        child=subprocess.Popen(command,stdin=subprocess.PIPE if config is not None else subprocess.DEVNULL,
            stdout=output,stderr=subprocess.STDOUT,env=env,start_new_session=True,close_fds=True)
    if config is not None:
        child.stdin.write((json.dumps(config)+'\n').encode())
        child.stdin.close()
    return child


def launch(config):
    python=os.path.abspath(config['python']) # Preserve the virtualenv executable path.
    root=Path(config['runsRoot']).resolve();root.mkdir(parents=True,exist_ok=True)
    logs=root/'service-logs';logs.mkdir(exist_ok=True)
    state=root/'services.json'
    old=json.loads(state.read_text()) if state.exists() else {}
    physical=bool(config.get('physicalToken'));simulation=bool(config.get('simulationToken'))
    roles=(['provider','physical'] if physical else [])+(['simulation'] if simulation else [])
    if not roles:raise ValueError('Configure at least one worker role')
    for role in roles:
        if role in old and running(old[role]['pid']):
            raise RuntimeError(role+' is already running; no process was changed')
    port=int(config.get('providerPort',8797))
    env=os.environ.copy()
    if physical:
        shared=Path(config['sharedRunner']).resolve()/'codex-runner'
        provider=shared/'roboskills_playground.py'
        if not provider.is_file():raise ValueError('sharedRunner must contain the BluPe RoboSkills provider')
        with socket.socket() as probe:probe.bind(('127.0.0.1',port))
        env['PYTHONPATH']=os.pathsep.join([str(shared/'src'),str(shared),env.get('PYTHONPATH','')])
    workers=Path(__file__).resolve().parent
    receipt={k:v for k,v in old.items() if k not in roles}
    children=[]
    def start(role,command,data):
        log=logs/(role+'.log')
        child=launch_process(command,data,log=log,env=env)
        children.append(child)
        receipt[role]={'pid':child.pid,'log':str(log),'startedAt':time.time()}
        state.write_text(json.dumps(receipt,indent=2)+'\n')
        return child
    if physical:
        provider_child=start('provider',[python,str(provider),'--port',str(port),
            '--recording-root',str(root/'physical-harness-recordings')],None)
        deadline=time.monotonic()+20
        while True:
            if provider_child.poll() is not None:raise RuntimeError('Provider exited; inspect its log before a new launch')
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:
                if time.monotonic()>deadline:raise RuntimeError('Provider not ready; inspect its log. It was not restarted.')
                time.sleep(.2)
        start('physical',[python,str(workers/'physical_worker.py')],{
            'origin':config['origin'],'workerToken':config['physicalToken'],'python':python,
            'runs':str(root/'physical-runs'),'harness':f'http://127.0.0.1:{port}'})
    if simulation:
        start('simulation',[python,str(workers/'worker.py')],{
            'origin':config['origin'],'workerToken':config['simulationToken'],'python':python,
            'runs':str(root/'simulation-runs'),'model':config.get('simulationModel','gpt-6-astra'),
            'hours':config.get('hours',1)})
    # Catch immediate configuration errors; subsequent readiness is the Site heartbeat.
    time.sleep(1)
    if any(child.poll() is not None for child in children):
        raise RuntimeError('A service exited; inspect the saved logs. No service was restarted.')
    return receipt


if __name__=='__main__':
    print(json.dumps(launch(read_config())),flush=True)
