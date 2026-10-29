#!/usr/bin/env python3
"""Prewarm native task coordinates without a controller, model run, or media encode."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from remote_yam.native_history import NativePastRuns
from remote_yam.task_cloud import TaskCloud, task_key


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes-root',action='append',required=True)
    parser.add_argument('--media-cache',required=True)
    parser.add_argument('--database',required=True,help='The service YAM_TASK_CLOUD_DATABASE path')
    args=parser.parse_args()
    seed=ROOT/'config/task-cloud-projection-v1.json'
    if not seed.is_file(): parser.error('Package is missing the shared frozen task projection')
    version=json.loads(seed.read_text())['version']
    started=time.monotonic()
    catalog=NativePastRuns(args.episodes_root,args.media_cache)
    rows=catalog.page(metadata=True)['runs']
    cloud=TaskCloud(args.database)
    encoded_tasks=0
    encode=cloud.encode
    def measured_encode(texts):
        nonlocal encoded_tasks
        result=encode(texts)
        encoded_tasks+=len(texts)
        return result
    cloud.encode=measured_encode
    cloud.index(rows)
    result=cloud.snapshot(rows)
    if result['version'] != version or result['missing']:
        raise SystemExit('Native task index did not use the complete shared frozen projection')
    print(json.dumps(dict(runs=len(rows),unique_tasks=len({task_key(row['prompt']) for row in rows}),
        version=result['version'],status=result['status'],elapsed_s=time.monotonic()-started,
        native_encoder_executed=encoded_tasks>0,encoded_tasks=encoded_tasks,
        media_encodes=0,robot_sessions=0)))


if __name__=='__main__':main()
