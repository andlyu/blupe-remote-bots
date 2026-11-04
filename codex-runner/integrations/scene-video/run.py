"""Reproducible offline preflight and normal playground entry points."""
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
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['verify','serve'])
    parser.add_argument('--runner-root',type=Path,required=True,help='Pinned shared codex-runner directory')
    parser.add_argument('--hardware-root',type=Path,help='Public controller runtime directory (offline guard only)')
    parser.add_argument('--output',type=Path,default=HERE/'recordings')
    parser.add_argument('--port',type=int,default=8796)
    args=parser.parse_args()
    runtime=json.loads((HERE/'data/runtime.json').read_text())
    runner=args.runner_root.resolve()
    for rel,expected in runtime['files'].items():
        if hashlib.sha256((runner/rel).read_bytes()).hexdigest()!=expected:
            parser.error('Shared runtime changed; use the pinned revision '+runtime['runner_revision'])
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(map(str,[runner,runner/'src',HERE])))
    output=args.output.resolve();simulation=output/'simulation'
    if args.mode=='verify':
        if args.hardware_root is None:parser.error('--hardware-root is required for offline guard verification')
        for rel,expected in runtime['controller_files'].items():
            if hashlib.sha256((args.hardware_root.resolve()/rel).read_bytes()).hexdigest()!=expected:
                parser.error('Offline controller snapshot changed; use '+runtime['controller_revision'])
        output.mkdir(parents=True,exist_ok=True)
        started=time.monotonic()
        subprocess.run([sys.executable,'-m','pytest','-q','-o',
            'cache_dir='+str(output/'pytest-cache'),str(HERE/'test_completion.py')],env=env,check=True)
        regression_s=time.monotonic()-started
        subprocess.run([sys.executable,str(HERE/'verify_sim.py'),'--output',str(simulation),
            '--calibration',str(HERE/'data/yam1-calibration.json'),
            '--home',str(HERE/'data/simulation-home.json'),
            '--hardware-root',str(args.hardware_root.resolve())],env=env,check=True)
        path=simulation/'verification.json';receipt=json.loads(path.read_text())
        receipt.update(completion_regressions_passed=True,regression_command_s=regression_s,
            runner_revision=runtime['runner_revision'],controller_revision=runtime['controller_revision'],
            verification_script_sha256=hashlib.sha256((HERE/'verify_sim.py').read_bytes()).hexdigest())
        path.write_text(json.dumps(receipt,indent=2))
        return
    receipt=json.loads((simulation/'verification.json').read_text())
    if not receipt.get('completion_regressions_passed'):
        parser.error('Run the full verify entry point before serving')
    report=json.loads((HERE/'data/yam1-calibration.json').read_text())
    os.execve(sys.executable,[sys.executable,str(HERE/'launch.py'),
        '--calibration-id',report['calibration_id'],'--simulation',str(simulation),
        '--output',str(output),'--port',str(args.port)],env)

if __name__=='__main__':main()
