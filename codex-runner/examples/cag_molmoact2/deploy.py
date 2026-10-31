"""Scoped, bounded RunPod trial using an explicitly prepared existing volume.

State is outside source control. Never mutates another endpoint, creates a
volume, or installs credentials into a worker. Unknown creates reconcile by
unique name, without retrying a POST blindly. No robot IO.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from config import IMAGE, gpu_config

KEY = Path.home() / '.config/runpod/api-key'


def api(path, body=None, method=None):
    req = Request('https://api.runpod.io/v2/' + path,
        data=None if body is None else json.dumps(body).encode(), method=method,
        headers={'Authorization': 'Bearer ' + KEY.read_text().strip(), 'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=45) as response:
            data = response.read()
            return json.loads(data) if data else {}
    except HTTPError as exc:
        # Response bodies can contain echoed private deployment arguments.
        raise RuntimeError(f'RunPod HTTP {exc.code}') from None


def inventory():
    items, cursor, seen = [], None, set()
    while True:
        value = api('serverless?limit=1000' + ('&cursor='+cursor if cursor else ''))
        items.extend(value['endpoints'])
        if not value.get('pagination', {}).get('hasNextPage'):
            return items
        cursor = value['pagination']['nextCursor']
        if cursor in seen:
            raise RuntimeError('Invalid pagination')
        seen.add(cursor)


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def owned(state):
    value = api('serverless/' + state['endpoint'])
    volumes = set(value.get('networkVolumes', [])) | {v['volumeId'] for v in value.get('mounts', {}).get('network', [])}
    if (value['id'] != state['endpoint'] or value['name'] != state['name'] or value['image'] != IMAGE
            or state['volume'] not in volumes or value['type'] != 'LOAD_BALANCER'):
        raise RuntimeError('Resource ownership mismatch; refusing mutation')
    return value


def patch(state, minimum, maximum):
    owned(state)
    value = api('serverless/'+state['endpoint'],
        {'workers': dict(min=minimum, max=maximum, idleTimeout=300)}, 'PATCH')
    return dict(endpoint=value['id'], workers=value['workers'])


def guard(path):
    while True:
        state = json.loads(path.read_text())
        if time.time() >= state['deadline']:
            try:
                result = patch(state, 0, 0)
                save(path.with_name('deadline-stop.json'), dict(time=time.time(), **result))
                return
            except Exception as exc:
                print(type(exc).__name__, flush=True)
        time.sleep(15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['provision', 'start', 'release', 'disable', 'status', 'health', 'guard', 'update', 'serve'])
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--volume')
    parser.add_argument('--name')
    args = parser.parse_args()
    path = args.state.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.action == 'guard':
        return guard(path)
    with path.with_suffix('.operation.lock').open('a') as operation:
        fcntl.flock(operation, fcntl.LOCK_EX)
        execute(args, path)


def execute(args, path):
    state = json.loads(path.read_text()) if path.exists() else {}
    if args.action == 'provision':
        if not args.name or not args.volume:
            parser.error('An explicit unique --name and prepared --volume are required')
        if state and (state['name'] != args.name or state['volume'] != args.volume):
            raise RuntimeError('Saved identity differs')
        state = state or dict(name=args.name, volume=args.volume, created_at=time.time())
        matches = [v for v in inventory() if v['name'] == args.name]
        if len(matches) > 1:
            raise RuntimeError('Ambiguous endpoint name')
        if matches:
            state['endpoint'] = matches[0]['id']
        elif state.get('create_attempted_at'):
            raise RuntimeError('Previous create outcome unknown; no duplicate POST')
        else:
            state['create_attempted_at'] = time.time()
            save(path, state)
            result = api('serverless', gpu_config(args.volume, args.name))
            state['endpoint'] = result['id']
        save(path, state)
        owned(state)
        print(json.dumps(state)); return
    owned(state)
    if args.action == 'serve':
        # Explicit persistent-service action. Never resets or renews a trial.
        if state.get('deadline') or state.get('mode') != 'on_demand':
            raise RuntimeError('Use a separate on_demand service record without a trial deadline')
        current=owned(state)
        if current['workers']['max'] != 0:
            raise RuntimeError('Disable this endpoint before configuring persistent service')
        for worker in api('serverless/'+state['endpoint']+'/workers').get('workers', []):
            if api('pods/'+worker['id']).get('status') not in ('EXITED','STOPPED','TERMINATED'):
                raise RuntimeError('Wait for zero active GPU workers before configuring persistent service')
        config=gpu_config(state['volume'],state['name'],persistent=True)
        value=api('serverless/'+state['endpoint'],
            {k:config[k] for k in ('entrypoint','cmd','env')} |
            {'workers':dict(min=0,max=1,idleTimeout=300)}, 'PATCH')
        save(path.with_name('service-enabled.json'),dict(enabled_at=time.time(),endpoint=value['id'],workers=value['workers'],mode='on_demand'))
        print(json.dumps(dict(endpoint=value['id'],workers=value['workers'],mode='on_demand')));return
    if args.action == 'update':
        current=owned(state)
        workers=api('serverless/'+state['endpoint']+'/workers')
        if current['workers']['max'] != 0:
            raise RuntimeError('Disable this endpoint before updating')
        for worker in workers.get('workers',[]):
            if worker['status'] != 'IDLE' or api('pods/'+worker['id']).get('status') not in ('EXITED','STOPPED','TERMINATED'):
                raise RuntimeError('Wait for zero active GPU workers before updating')
        config=gpu_config(state['volume'],state['name'])
        value=api('serverless/'+state['endpoint'], {'entrypoint':config['entrypoint'],'cmd':config['cmd']}, 'PATCH')
        print(json.dumps(dict(endpoint=value['id'],updated=True)));return
    if args.action == 'start':
        if state.get('deadline') and time.time() >= state['deadline']:
            raise RuntimeError('Trial expired; deadline cannot be reset')
        if not state.get('deadline'):
            state['deadline'] = time.time()+3600
            save(path, state)
        # Install independent deadline guard BEFORE enabling paid workers.
        pid = state.get('guard_pid')
        try:
            if not pid:
                raise ProcessLookupError()
            os.kill(pid, 0)
        except ProcessLookupError:
            with path.with_name('guard.log').open('a') as log:
                child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'guard', '--state', str(path)],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            state['guard_pid'] = child.pid
            save(path, state)
        print(json.dumps(patch(state, 1, 1))); return
    if args.action in ('release', 'disable'):
        if args.action == 'release' and (not state.get('deadline') or time.time() >= state['deadline']):
            raise RuntimeError('An active bounded trial is required; expired trials cannot be re-enabled')
        print(json.dumps(patch(state, 0, int(args.action == 'release')))); return
    if args.action == 'status':
        workers = api('serverless/'+state['endpoint']+'/workers')
        for worker in workers.get('workers', []):
            try:
                worker['pod_status'] = api('pods/'+worker['id']).get('status')
            except RuntimeError:
                worker['pod_status'] = 'unknown'
        save(path.with_name('workers-latest.json'), workers)
        print(json.dumps(workers)); return
    req = Request('https://'+state['endpoint']+'.api.runpod.ai/health',
        headers={'Authorization': 'Bearer '+KEY.read_text().strip()})
    started = time.monotonic()
    with urlopen(req, timeout=330) as response:
        value = json.load(response)
    save(path.with_name('health.json'), dict(client_seconds=time.monotonic()-started, result=value))
    print(json.dumps(value))


if __name__ == '__main__':
    main()
