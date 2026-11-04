#!/usr/bin/env python3
"""Task-scoped saved-file transfer. No cameras, control lease or motor access.

Runs on the existing YAM1 preview worker runtime; imports its unchanged idle,
video, storage and memory gate. Cloud uses the existing canonical publisher.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

TASK='Record a multi-view scene episode with the guided capture preset.'
FILES=('manifest.json','samples.jsonl','images.tar','image-index.jsonl')


def read(path):return json.loads(Path(path).read_text())

def write(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value)+'\n');tmp.replace(path)

def eligible(episode,since):
    m=read(episode/'manifest.json')
    if (not re.fullmatch('ep_[A-Za-z0-9_-]+',episode.name) or m.get('episode_id')!=episode.name
            or m.get('task')!=TASK or m.get('status')!='finalized' or m.get('simulated')
            or m.get('started_at',0)<since or not re.fullmatch('[a-f0-9]{64}',m.get('samples_sha256',''))):
        return False
    state=read(episode/'scene-upload.json') if (episode/'scene-upload.json').exists() else {}
    return state.get('status')!='uploaded' and state.get('retry_at',0)<=time.time()


def progress(eid,state,message):
    path=Path('/var/lib/blupe-path-studio/scene-capture-public')/(eid+'.status.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    write(path,dict(episode_id=eid,status=state,message=message,updated_at=time.time()))


def cloud(root):
    from scripts.publish_yam_training import publish_once
    from huggingface_hub import HfApi,hf_hub_download,CommitOperationAdd
    for episode in root.glob('ep_*'):
        if not eligible(episode,0):continue
        progress(episode.name,'exporting','Saved recording received. Exporting three native camera videos and joint data…')
        manifest=read(episode/'manifest.json')
        if hashlib.sha256((episode/'samples.jsonl').read_bytes()).hexdigest()!=manifest['samples_sha256']:
            raise ValueError('Source samples checksum mismatch')
        if hashlib.sha256((episode/'image-index.jsonl').read_bytes()).hexdigest()!=manifest['image_index_sha256']:
            raise ValueError('Source image index checksum mismatch')
        # Extract only relative regular files into the dedicated saved-data dir.
        with tarfile.open(episode/'images.tar') as archive:
            members=archive.getmembers()
            if any(not m.isfile() or Path(m.name).is_absolute() or '..' in Path(m.name).parts
                   or not m.name.startswith('images/') for m in members):
                raise ValueError('Unsafe image archive entry')
            archive.extractall(episode,members=members,filter='data')
        receipt=read(episode/'capture-receipt.json')
        if receipt.get('episode_id')!=episode.name:raise ValueError('Capture receipt mismatch')
        rows=[json.loads(line) for line in (episode/'samples.jsonl').read_text().splitlines() if line]
        if len(rows)!=manifest['rows']:raise ValueError('Source row count mismatch')
        # Canonical publisher retains all rows, all three native videos, 14D
        # measured/commanded vectors, source timestamps and quality flags.
        os.environ.pop('YAM_VIEWING_FIRST_SINCE',None)
        progress(episode.name,'publishing','Encoding and publishing the complete HF episode. The arms will not run again.')
        previous=read(episode/'upload.json') if (episode/'upload.json').exists() else {}
        if previous.get('status')=='uploaded' and previous.get('lerobot_version')=='v2.1':
            result=previous
        else:
            results=publish_once(root,limit=1)
            if not results or results[0].get('episode_id')!=episode.name or results[0]['status']!='uploaded':
                raise RuntimeError('Canonical full episode publisher did not complete')
            result=results[0]
        api=HfApi();repo='andlyu/Public-YAM-runs'
        revision=result['commit'];index=result['lerobot_episode_index'];stem=f'chunk-{index//1000:03d}';name=f'episode_{index:06d}'
        paths=[f'data/{stem}/{name}.parquet',*[f'videos/{stem}/observation.images.{a}/{name}.mp4' for a in ('left','top','right')]]
        # Read back every native stream and joint table; preserve checksum proof.
        hashes={path:hashlib.sha256(Path(hf_hub_download(repo,path,repo_type='dataset',revision=revision)).read_bytes()).hexdigest() for path in paths}
        verification=dict(episode_id=episode.name,episode_index=index,rows=len(rows),source_samples_sha256=manifest['samples_sha256'],verified_file_sha256=hashes,commit=revision)
        cal=json.dumps(receipt['calibration'],indent=2).encode();evidence=json.dumps({**receipt,'publication':verification},indent=2).encode()
        commit=api.create_commit(repo_id=repo,repo_type='dataset',parent_commit=revision,
            commit_message=f'Attach scene capture verification for {episode.name}',operations=[
            CommitOperationAdd(path_in_repo=f'calibration/{episode.name}.json',path_or_fileobj=cal),
            CommitOperationAdd(path_in_repo=f'captures/{episode.name}.scene-capture.json',path_or_fileobj=evidence)])
        progress(episode.name,'published','Full HF episode published and all native file hashes checked.')
        write(episode/'scene-upload.json',dict(status='uploaded',episode_id=episode.name,episode_index=index,commit=commit.oid,samples_sha256=manifest['samples_sha256'],verified_file_sha256=hashes,uploaded_at=time.time()))


def one(args):
    episode=args.episode
    if not eligible(episode,args.since):return
    meta=read(episode/'manifest.json')
    if sum((episode/f).stat().st_size for f in FILES)>512*1024**2:raise ValueError('Saved episode exceeds 512 MiB transfer bound')
    url='https://d39laae2ep8en8.cloudfront.net/api/path-studio/capture/receipt?id='+episode.name
    with urlopen(url,timeout=10) as response:receipt=json.load(response)
    if receipt.get('episode_id')!=episode.name:raise ValueError('Website capture receipt unavailable')
    write(episode/'capture-receipt.json',receipt)
    ssh=shlex.split(args.ssh);remote=args.cloud_root+'/'+episode.name
    status_code='from pathlib import Path; import json,time; p=Path("/var/lib/blupe-path-studio/scene-capture-public")/'+repr(episode.name+'.status.json')+'; p.write_text(json.dumps(dict(status="transferring",message="Transferring the saved episode to the full HF publisher; waiting for idle robot storage and healthy cameras.",updated_at=time.time())))'
    subprocess.run([*ssh,args.host,shlex.join(['python3','-c',status_code])],check=True,timeout=20)
    command='mkdir -p '+shlex.quote(remote)+' && test $(df -Pk '+shlex.quote(args.cloud_root)+" | awk 'NR==2 {print $4}') -gt 1048576"
    subprocess.run([*ssh,args.host,command],check=True,timeout=20)
    subprocess.run(['rsync','-a','--partial','--bwlimit=6000','-e',args.ssh,
        *[str(episode/f) for f in (*FILES,'capture-receipt.json')],args.host+':'+remote+'/'],check=True,timeout=180)
    cloud_cmd=' '.join(shlex.quote(v) for v in ['/usr/bin/env','PYTHONPATH=/home/ubuntu/blupe-publisher','HF_TOKEN_PATH=/home/ubuntu/.config/blupe-dataset/hf_token',
        '/home/ubuntu/blupe-publisher/.venv/bin/python',args.cloud_script,'cloud','--root',args.cloud_root])
    subprocess.run([*ssh,args.host,cloud_cmd],check=True,timeout=900)
    result=subprocess.run([*ssh,args.host,'cat '+shlex.quote(remote+'/scene-upload.json')],check=True,capture_output=True,text=True,timeout=20)
    receipt=json.loads(result.stdout)
    if receipt.get('status')!='uploaded' or receipt.get('samples_sha256')!=meta['samples_sha256']:raise ValueError('Publication receipt mismatch')
    write(episode/'scene-upload.json',receipt)


def watch(args):
    from scripts.yam_preview_uploads import ready
    from scripts.yam_export_scheduler import stop_worker
    args.state.mkdir(parents=True,exist_ok=True)
    child=None;idle_since=None;current=None
    def ending(*_):raise SystemExit()
    signal.signal(signal.SIGTERM,ending);signal.signal(signal.SIGINT,ending)
    with (args.state/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            while True:
                healthy=ready(args.root,args.health);now=time.monotonic()
                if child and child.poll() is not None:
                    stop_worker(child)
                    if child.returncode and current:
                        write(current/'scene-upload.json',dict(status='retrying',retry_at=time.time()+60,error='Saved-file export failed; motion will not be replayed'))
                    child=None
                if not healthy:
                    idle_since=None
                    if child and stop_worker(child):child=None
                else:
                    idle_since=idle_since or now
                    if not child and now-idle_since>=5:
                        for episode in sorted(args.root.glob('ep_*')):
                            try:ok=eligible(episode,args.since)
                            except (OSError,ValueError):continue
                            if ok:
                                current=episode
                                command=[sys.executable,__file__,'one','--episode',str(episode),'--since',str(args.since),'--ssh',args.ssh,'--host',args.host,'--cloud-root',args.cloud_root,'--cloud-script',args.cloud_script]
                                child=subprocess.Popen(command,start_new_session=True);break
                write(args.state/'status.json',dict(timestamp=time.time(),state='processing' if child else 'waiting_for_idle' if not healthy else 'watching',episode_id=current.name if child else None))
                time.sleep(2)
        finally:
            if child:stop_worker(child)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['watch','one','cloud'])
    parser.add_argument('--root',type=Path);parser.add_argument('--episode',type=Path);parser.add_argument('--since',type=float,default=0)
    parser.add_argument('--health',type=Path,default=Path('/run/user/1000/yam-synchronized-hd-health.json'))
    parser.add_argument('--state',type=Path,default=Path('/home/andrew/.local/state/scene-capture-upload'))
    parser.add_argument('--host',default='ubuntu@54.209.185.15');parser.add_argument('--ssh',default='/usr/bin/ssh -i /home/andrew/.ssh/aws_apr_25_key.pem -o UserKnownHostsFile=/home/andrew/.ssh/yam_operator_known_hosts -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5')
    parser.add_argument('--cloud-root',default='/home/ubuntu/blupe-publisher/scene-capture-episodes')
    parser.add_argument('--cloud-script',default='/opt/blupe-path-studio/current/codex-runner/scene_capture_upload.py')
    args=parser.parse_args()
    if args.mode=='cloud':
        args.root.mkdir(parents=True,exist_ok=True)
        with (args.root/'.worker.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:cloud(args.root)
            except Exception:
                for episode in args.root.glob('ep_*'):
                    if not (episode/'scene-upload.json').exists():progress(episode.name,'retrying','Saved-data export or publication failed. It will retry without moving the arms.')
                raise
    elif args.mode=='one':one(args)
    else:watch(args)
if __name__=='__main__':main()
