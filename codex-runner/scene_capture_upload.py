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


def publisher_preflight():
    import inspect
    from importlib.metadata import version
    import shutil
    from scripts import publish_yam_training as publisher
    from YAM_control import lerobot_dataset,direct_episode_storage
    from datasets import Dataset
    import pyarrow
    from PIL import Image
    inspect.signature(publisher.publish_once).bind(Path('/saved'))
    assert callable(direct_episode_storage.RecordingImages)
    assert callable(lerobot_dataset.append_episode)
    if not shutil.which('ffmpeg'):raise RuntimeError('Full-episode export needs ffmpeg')
    return dict(publisher_signature=str(inspect.signature(publisher.publish_once)),
        files_sha256={module.__name__:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (publisher,lerobot_dataset,direct_episode_storage)},
        versions={package:version(package) for package in ('datasets','pyarrow','Pillow','huggingface-hub')})


def publish_selected(publisher,root,eid):
    # Both installed canonical publisher versions support root; the deployed
    # version intentionally has no limit keyword. Never downgrade the export.
    result=next((r for r in publisher(root) if r.get('episode_id')==eid),None)
    if not result or result.get('status')!='uploaded':
        raise RuntimeError('Canonical full episode publisher did not complete')
    return result


def cloud(root):
    environment=publisher_preflight()
    os.environ['YAM_FFMPEG']=str(Path(__file__).with_name('scene_capture_ffmpeg.py'))
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
            result=publish_selected(publish_once,root,episode.name)
        api=HfApi();repo='andlyu/Public-YAM-runs'
        revision=result['commit'];index=result['lerobot_episode_index'];stem=f'chunk-{index//1000:03d}';name=f'episode_{index:06d}'
        paths=[f'data/{stem}/{name}.parquet',*[f'videos/{stem}/observation.images.{a}/{name}.mp4' for a in ('left','top','right')]]
        # Read back every native stream and joint table; preserve checksum proof.
        hashes={path:hashlib.sha256(Path(hf_hub_download(repo,path,repo_type='dataset',revision=revision)).read_bytes()).hexdigest() for path in paths}
        import numpy as np
        import pyarrow.parquet as pq
        from YAM_control.lerobot_dataset import state_vector
        columns=pq.read_table(hf_hub_download(repo,paths[0],repo_type='dataset',revision=revision)).to_pydict()
        if len(columns['frame_index'])!=len(rows):raise ValueError('Native episode row count differs')
        for i,row in enumerate(rows):
            for key,values in (('observation.state',state_vector(row['measured_joints'],row['measured_grippers'])),('action',state_vector(row['action_joints'],row['action_grippers']))):
                if not np.array_equal(np.asarray(columns[key][i],np.float32),np.asarray(values,np.float32)):
                    raise ValueError('Native joint vector differs from saved row')
            if columns['source_timestamp'][i]!=row['timestamp'] or columns['training_valid'][i]!=row['training_valid'] or columns['action_valid'][i]!=row['action_valid']:
                raise ValueError('Native timing or quality flags differ')
            for arm in ('left','top','right'):
                for suffix in ('frame_sequence','camera_timestamp','frame_age_s'):
                    key=arm+'_'+suffix
                    if np.float32(columns[key][i])!=np.float32(row[key]):raise ValueError('Native camera alignment differs')
        video_checks={}
        for arm,path in zip(('left','top','right'),paths[1:]):
            native=hf_hub_download(repo,path,repo_type='dataset',revision=revision)
            probe=subprocess.run(['ffprobe','-v','error','-count_frames','-show_entries','stream=nb_read_frames,width,height,r_frame_rate','-of','json',native],check=True,capture_output=True,text=True)
            stream=json.loads(probe.stdout)['streams'][0]
            if int(stream['nb_read_frames'])!=len(rows) or stream['r_frame_rate']!='10/1':raise ValueError('Native camera video frame clock differs')
            video_checks[arm]=stream
        verification=dict(native_rows_match_saved_samples=True,video_streams=video_checks,publisher_environment=environment,episode_id=episode.name,episode_index=index,rows=len(rows),source_samples_sha256=manifest['samples_sha256'],verified_file_sha256=hashes,commit=revision)
        cal=json.dumps(receipt['calibration'],indent=2).encode();evidence=json.dumps({**receipt,'publication':verification},indent=2).encode()
        current=api.repo_info(repo_id=repo,repo_type='dataset').sha
        registry=Path(hf_hub_download(repo,'meta/blupe_source_episodes.jsonl',repo_type='dataset',revision=current))
        entry=next(json.loads(line) for line in registry.read_text().splitlines() if json.loads(line).get('episode_id')==episode.name)
        if entry['episode_index']!=index or entry['samples_sha256']!=manifest['samples_sha256']:raise ValueError('Current registry differs from verified source')
        commit=api.create_commit(repo_id=repo,repo_type='dataset',parent_commit=current,
            commit_message=f'Attach scene capture verification for {episode.name}',operations=[
            CommitOperationAdd(path_in_repo=f'calibration/{episode.name}.json',path_or_fileobj=cal),
            CommitOperationAdd(path_in_repo=f'captures/{episode.name}.scene-capture.json',path_or_fileobj=evidence)])
        progress(episode.name,'published','Full HF episode published and all native file hashes checked.')
        write(episode/'scene-upload.json',dict(status='uploaded',episode_id=episode.name,episode_index=index,commit=commit.oid,samples_sha256=manifest['samples_sha256'],verified_file_sha256=hashes,native_rows_match_saved_samples=True,video_streams=video_checks,uploaded_at=time.time()))


def one(args):
    episode=args.episode
    if not eligible(episode,args.since):return
    meta=read(episode/'manifest.json')
    ssh=shlex.split(args.ssh);remote=args.cloud_root+'/'+episode.name
    unit='blupe-scene-publish-'+episode.name
    probe_code='import json,subprocess; from pathlib import Path; p=Path('+repr(remote+'/scene-upload.json')+'); print(p.read_text() if p.exists() else json.dumps(dict(status="pending",active=subprocess.run(["systemctl","is-active","--quiet",'+repr(unit)+']).returncode==0)))'
    probe=subprocess.run([*ssh,args.host,shlex.join(['python3','-c',probe_code])],check=True,capture_output=True,text=True,timeout=20)
    state=json.loads(probe.stdout)
    if state.get('status')=='uploaded':
        if state.get('samples_sha256')!=meta['samples_sha256']:raise ValueError('Publication receipt mismatch')
        write(episode/'scene-upload.json',state);return
    if state.get('active'):
        write(episode/'scene-upload.json',dict(status='publishing',retry_at=time.time()+30));return
    if sum((episode/f).stat().st_size for f in FILES)>512*1024**2:raise ValueError('Saved episode exceeds 512 MiB transfer bound')
    url='https://d39laae2ep8en8.cloudfront.net/api/path-studio/capture/receipt?id='+episode.name
    with urlopen(url,timeout=10) as response:receipt=json.load(response)
    if receipt.get('episode_id')!=episode.name:raise ValueError('Website capture receipt unavailable')
    write(episode/'capture-receipt.json',receipt)
    status_code='from pathlib import Path; import json,time; p=Path("/var/lib/blupe-path-studio/scene-capture-public")/'+repr(episode.name+'.status.json')+'; old=json.loads(p.read_text()) if p.exists() else {}; keep=old.get("status") in ("publishing","exporting") and time.time()-old.get("updated_at",0)<900; p.write_text(json.dumps(old if keep else dict(status="transferring",message="Transferring the saved episode to the full HF publisher; waiting for idle robot storage and healthy cameras.",updated_at=time.time())))'
    subprocess.run([*ssh,args.host,shlex.join(['python3','-c',status_code])],check=True,timeout=20)
    command='mkdir -p '+shlex.quote(remote)+' && test $(df -Pk '+shlex.quote(args.cloud_root)+" | awk 'NR==2 {print $4}') -gt 1048576"
    subprocess.run([*ssh,args.host,command],check=True,timeout=20)
    subprocess.run(['rsync','-a','--partial','--bwlimit=6000','-e',args.ssh,
        *[str(episode/f) for f in (*FILES,'capture-receipt.json')],args.host+':'+remote+'/'],check=True,timeout=180)
    # After transfer, rendering belongs to a bounded cloud job. A source idle
    # guard can cancel SSH/rsync without killing cloud FFmpeg or losing progress.
    command=['sudo','systemd-run','--unit',unit,'--collect','--uid=ubuntu',
        '--property=WorkingDirectory=/home/ubuntu/blupe-publisher',
        '--property=RuntimeMaxSec=900','--property=MemoryMax=768M','--property=CPUQuota=80%',
        '--property=Nice=10','--setenv=PYTHONPATH=/home/ubuntu/blupe-publisher',
        '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=HF_TOKEN_PATH=/home/ubuntu/.config/blupe-dataset/hf_token',
        '/home/ubuntu/blupe-publisher/.venv/bin/python',args.cloud_script,'cloud','--root',args.cloud_root]
    subprocess.run([*ssh,args.host,shlex.join(command)],check=True,timeout=20)
    write(episode/'scene-upload.json',dict(status='publishing',retry_at=time.time()+30,
        message='Saved data transferred; independent cloud publication running'))


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
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['watch','one','cloud','preflight'])
    parser.add_argument('--root',type=Path);parser.add_argument('--episode',type=Path);parser.add_argument('--since',type=float,default=0)
    parser.add_argument('--health',type=Path,default=Path('/run/user/1000/yam-synchronized-hd-health.json'))
    parser.add_argument('--state',type=Path,default=Path('/home/andrew/.local/state/scene-capture-upload'))
    parser.add_argument('--host',default='ubuntu@54.209.185.15');parser.add_argument('--ssh',default='/usr/bin/ssh -i /home/andrew/.ssh/aws_apr_25_key.pem -o UserKnownHostsFile=/home/andrew/.ssh/yam_operator_known_hosts -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5')
    parser.add_argument('--cloud-root',default='/home/ubuntu/blupe-publisher/scene-capture-episodes')
    parser.add_argument('--cloud-script',default='/opt/blupe-path-studio/current/codex-runner/scene_capture_upload.py')
    args=parser.parse_args()
    if args.mode=='preflight':print(json.dumps(publisher_preflight(),indent=2));return
    if args.mode=='cloud':
        args.root.mkdir(parents=True,exist_ok=True)
        with (args.root/'.worker.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:cloud(args.root)
            except Exception:
                for episode in args.root.glob('ep_*'):
                    if not (episode/'scene-upload.json').exists():progress(episode.name,'retrying','Saved-data export or publication failed. It will retry without moving the arms.')
                raise
    elif args.mode=='one':one(args)
    else:watch(args)
if __name__=='__main__':main()
