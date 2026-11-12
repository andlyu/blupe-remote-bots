#!/usr/bin/env python3
"""Required offline release gate: real generator/serializer and Kinex MCP."""
import argparse,hashlib,json,os
from pathlib import Path
import subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[2]
SOURCES=['src/remote_yam/kinex_policy.py','src/remote_yam/session.py','src/remote_yam/controller.py',
 'src/remote_yam/mujoco_ik.py','tests/test_kinex.py',
 'integrations/kinex/agent.py','integrations/kinex/preflight.py',
 *['integrations/kinex/runtime/'+name for name in ('driver.py','mcp.mjs','workspace.mjs','offline-mcp.mjs','yam1-limits.json')]]
def hashes():return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}
def upstream_fingerprint(path):
    root=Path(path).resolve()
    names=['package-lock.json','release.json','vendor/core.json','vendor/setup.json','node_modules/@openai/codex/package.json']
    names += [str(p.relative_to(root)) for directory in ('node_modules/@kinex/core','node_modules/@kinex/setup','packages/mcp/dist') for p in sorted((root/directory).rglob('*')) if p.is_file()]
    return dict(revision=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),
        sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names})

def verify(path,upstream=None):
    value=json.loads(Path(path).read_text())
    if value.get('status')!='passed' or value.get('source_sha256')!=hashes():raise ValueError('Kinex release preflight missing or stale; Run disabled')
    if upstream is not None and value.get('upstream_fingerprint')!=upstream_fingerprint(upstream):raise ValueError('Kinex upstream/runtime differs from the verified release; Run disabled')
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--upstream',required=True);a=p.parse_args()
    env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),KINEX_SOURCE=str(Path(a.upstream).resolve()),BLUPE_KINEX_PYTHON=sys.executable)
    records=[];started=time.time()
    commands=[[sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_kinex.py','-v']]
    with tempfile.TemporaryDirectory(prefix='kinex-release-') as workspace:
        sys.path.insert(0,str(ROOT/'src'));from remote_yam.kinex_policy import KinexPackets
        config={'directory':workspace,'limits':KinexPackets().limits,'cameras':{x:dict(width=640,height=480) for x in ('top','left','right')}}
        setup=subprocess.run(['node',str(ROOT/'integrations/kinex/runtime/workspace.mjs')],input=json.dumps(config),text=True,capture_output=True,env=env)
        if setup.returncode:raise RuntimeError(setup.stderr)
        commands.append(['node',str(ROOT/'integrations/kinex/runtime/offline-mcp.mjs'),workspace])
        for command in commands:
            begin=time.monotonic();r=subprocess.run(command,cwd=ROOT.parent,env=env,text=True,capture_output=True)
            records.append(dict(command=command,exit_code=r.returncode,runtime_s=time.monotonic()-begin,output=r.stdout+r.stderr))
            if r.returncode:break
    value=dict(status='passed' if all(r['exit_code']==0 for r in records) and len(records)==2 else 'failed',
        created_at=started,source_sha256=hashes(),commands=records,
        upstream_revision=subprocess.check_output(['git','-C',a.upstream,'rev-parse','HEAD'],text=True).strip(),
        upstream_fingerprint=upstream_fingerprint(a.upstream),
        validator='remote_yam.session._trajectory_waypoints and HttpSessionAPI.submit_trajectory',
        physical_commands_sent=0,simulation_rollout=False)
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(dict(status=value['status'],output=str(out),elapsed_s=time.time()-started)))
    raise SystemExit(0 if value['status']=='passed' else 1)
if __name__=='__main__':main()
