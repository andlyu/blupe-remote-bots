"""One command to verify, then serve the one-minute camera capture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['verify','serve'])
    parser.add_argument('--runner-root',type=Path,required=True)
    parser.add_argument('--hardware-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--identity-file',type=Path)
    parser.add_argument('--port',type=int,default=8797)
    args=parser.parse_args()
    runtime=json.loads((HERE/'data/runtime.json').read_text())
    for root,files in [(args.runner_root,runtime['files']),(args.hardware_root,runtime['controller_files'])]:
        for name,digest in files.items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
                parser.error('Pinned runtime/controller source changed: '+name)
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,[args.runner_root,args.runner_root/'src',HERE])),
             SCENE_HARDWARE_ROOT=str(args.hardware_root.resolve()))
    output=args.output.resolve();simulation=output/'simulation'
    if args.mode=='verify':
        output.mkdir(parents=True,exist_ok=True);started=time.monotonic()
        subprocess.run([sys.executable,'-m','pytest','-q','-o','cache_dir='+str(output/'pytest-cache'),
                        str(HERE/'test_completion.py'),str(HERE/'test_minute.py')],env=env,check=True)
        regression_s=time.monotonic()-started
        subprocess.run([sys.executable,str(HERE/'viewpoint_sim.py'),'--output',str(simulation),
                        '--hardware-root',str(args.hardware_root.resolve())],env=env,check=True)
        receipt=json.loads((simulation/'verification.json').read_text())
        receipt.update(minute_regressions_passed=True,regression_command_s=regression_s,
            launch_source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                for name in ('minute_policy.py','viewpoint_sim.py','scene_video.py')},
            runner_revision=runtime['runner_revision'],controller_revision=runtime['controller_revision'])
        (simulation/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n');return
    receipt=json.loads((simulation/'verification.json').read_text())
    if not receipt.get('minute_regressions_passed'):parser.error('Run minute.py verify before serving')
    command=[sys.executable,str(HERE/'launch_minute.py'),'--simulation',str(simulation),
        '--hardware-root',str(args.hardware_root.resolve()),'--output',str(output),'--port',str(args.port)]
    if args.identity_file:command+=['--identity-file',str(args.identity_file.resolve())]
    os.execve(sys.executable,command,env)

if __name__=='__main__':main()
