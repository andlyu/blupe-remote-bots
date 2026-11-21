"""Kinex JSONL device driver over the lease-fenced local BluPe bridge."""
import json
import base64
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from kinex.driver_protocol import check_cancelled, run

PROFILE = Path(__file__).parent.name


def dispatch(action, args):
    if action in ('load', 'status', 'unload'):
        return {'ok': True, 'loaded': action != 'unload'}
    if PROFILE == 'world':
        start = time.monotonic()
        if action == 'wait':
            if set(args) != {'duration_s'} or type(args['duration_s']) not in (int, float) or not 0 <= args['duration_s'] <= 60:
                raise ValueError('World waits require a finite duration in [0, 60] seconds')
            while time.monotonic() - start < args['duration_s']:
                check_cancelled()
                time.sleep(.025)
        elif action != 'read' or args:
            raise ValueError('Unsupported clock operation')
        return {'ok': True, 'time_s': time.monotonic(), **({'waited_s': time.monotonic()-start} if action == 'wait' else {})}
    request = Request(os.environ['BLUPE_KINEX_BRIDGE'] + '/device',
        data=json.dumps({'device': PROFILE, 'action': action, 'args': args}, allow_nan=False).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ['BLUPE_KINEX_TOKEN']})
    with urlopen(request, timeout=20) as response:
        result = json.load(response)
    if result.get('error'):
        raise RuntimeError(result['error'])
    if PROFILE.endswith('_camera') and action=='read' and args.get('output')=='file':
        directory=Path(__file__).parent/'out';directory.mkdir(exist_ok=True)
        path=directory/('frame-'+str(time.time_ns())+'.png');path.write_bytes(base64.b64decode(result.pop('color'),validate=True));result['file']=str(path)
    return result


if __name__ == '__main__':
    # Host shutdown owns Stop; unloading a camera must not park another device.
    run(dispatch, lambda: None)
