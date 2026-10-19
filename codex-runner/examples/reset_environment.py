#!/usr/bin/env python3
"""Select a configured reset policy through the normal Playground Run/status/Stop API."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from remote_yam.runner_policy_client import RunnerPolicyClient


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',default='http://127.0.0.1:8787')
    parser.add_argument('--robot-id',default='yam-1')
    parser.add_argument('--policy',default='reset_bin')
    parser.add_argument('--runner-name',default='API operator',help='Name attached to this run')
    parser.add_argument('--email',help='Email required by hosted guest admission; not needed for a local runner')
    parser.add_argument('--session-file',type=Path,help='Private visitor capability file for later status/Stop')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--start',action='store_true',help='Start real execution once; no automatic retry')
    action.add_argument('--status',action='store_true')
    action.add_argument('--stop',action='store_true')
    parser.add_argument('--wait',action='store_true',help='Poll after start; Ctrl-C requests Stop')
    args=parser.parse_args(argv)
    if (args.status or args.stop) and not args.session_file:parser.error('status/Stop require the original --session-file')
    client=RunnerPolicyClient.load(args.session_file) if args.status or args.stop else RunnerPolicyClient(args.origin,args.robot_id)
    if args.status or args.stop:
        print(json.dumps(client.stop() if args.stop else client.status(),indent=2));return 0
    metadata=client.connect()
    if args.session_file:client.save(args.session_file)
    if not args.start:
        print(json.dumps(dict(robot_id=metadata['robot_id'],configured_providers=metadata.get('configured_providers',{})),indent=2));return 0
    if not args.session_file and not args.wait:parser.error('start requires --wait or a --session-file to retain status/Stop authority')
    try:
        try:result=client.start(args.policy,runner_name=args.runner_name,email=args.email)
        finally:
            if args.session_file:client.save(args.session_file)
        print(json.dumps(result),flush=True)
        if args.wait:
            previous=None
            while True:
                state=client.status()
                summary={key:state.get(key) for key in ('attempt_id','status','error')}
                summary['execution']=(state.get('provider') or {}).get('managed_execution')
                encoded=json.dumps(summary)
                if encoded!=previous:print(encoded,flush=True);previous=encoded
                if state['status'] not in ('queued','preparing','running'):
                    return 0 if (summary['execution'] or {}).get('phase')=='complete' else 2
                time.sleep(.5)
        return 0
    except KeyboardInterrupt:
        print(json.dumps(client.stop()),flush=True)
        print('Stop requested; use the same session file to confirm terminal status.',file=sys.stderr)
        return 130


if __name__=='__main__':raise SystemExit(main())
