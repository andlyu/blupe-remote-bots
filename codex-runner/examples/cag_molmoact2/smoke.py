"""Non-motion, same-input A/zero/B inference check against the deployed service."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from remote_yam.molmoact_protocol import identity,validate_payload,validate_actions
from remote_yam.molmoact_policy import VARIANT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',required=True)
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--key-file',type=Path,default=Path.home()/'.config/runpod/api-key')
    args=parser.parse_args()
    # Reuse the adapter's host/redirect policy before adding authorization.
    from remote_yam.molmoact_policy import MolmoActAdapter
    adapter=MolmoActAdapter(args.key_file.expanduser().read_text(),camera_source=None,endpoint=args.endpoint)
    payload=json.loads(args.payload.read_text());validate_payload(payload)
    records=[]
    for mode,strength in [('baseline',0.),('guided',0.),('guided',.15)]:
        started=time.monotonic()
        value=adapter._json('/act',dict(payload,mode=mode,guidance_strength=strength,seed=0))
        adapter._identity(value);validate_actions(value['actions'])
        if value['experiment']['variant'] != VARIANT or value['experiment']['effective_strength'] != strength:
            raise RuntimeError('Intervention identity mismatch')
        records.append(dict(client_seconds=time.monotonic()-started,result=value))
    a,z,b=[r['result'] for r in records]
    equal=a['actions']==z['actions']
    unchanged=b['experiment']['non_goal_kv_unchanged']
    if not equal or not unchanged or b['experiment']['kv_delta_l1']<=0:
        raise RuntimeError('Comparison verification failed')
    summary=dict(identity(),variant=VARIANT,zero_strength_exact_equal=equal,
        non_goal_kv_unchanged=unchanged, nonzero_text_kv_changed=True,
        action_max_abs_delta=max(abs(x-y) for ar,br in zip(a['actions'],b['actions']) for x,y in zip(ar,br)),
        client_seconds=[r['client_seconds'] for r in records],
        inference_seconds=[r['result']['inference_seconds'] for r in records],
        dispatched_robot_commands=0)
    args.output.write_text(json.dumps(dict(summary=summary,records=records),indent=2))
    print(json.dumps(summary))


if __name__=='__main__':main()
