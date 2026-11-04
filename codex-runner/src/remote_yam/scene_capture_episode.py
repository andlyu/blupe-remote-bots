"""Resolve a source episode to its complete, immutable public HF bundle."""
import json
import re
import threading
import time
from urllib.request import Request,urlopen

REPO='andlyu/Public-YAM-runs'
_cache={};_lock=threading.Lock()


def _fetch(path,revision='main',head=False):
    url=f'https://huggingface.co/datasets/{REPO}/resolve/{revision}/{path}'
    with urlopen(Request(url,method='HEAD' if head else 'GET'),timeout=12) as response:
        body=response.read(4_000_001) if not head else b''
        if len(body)>4_000_000:raise ValueError('Episode metadata exceeds size limit')
        return body,response.headers.get('X-Repo-Commit')


def _resolve(eid):
    try:
        body,revision=_fetch('meta/blupe_source_episodes.jsonl')
        if not revision or not re.fullmatch('[a-f0-9]{40}',revision):
            raise ValueError('Cannot pin dataset revision')
        entries=[json.loads(line) for line in body.splitlines() if line]
        entry=next((r for r in entries if r.get('episode_id')==eid),None)
        if not entry:
            result=dict(status='awaiting_publication',episode_id=eid,message='Waiting for saved recording → full HF episode export. The arms will not run again.')
        else:
            index=entry['episode_index']
            if type(index) is not int or not 0<=index<10000000:raise ValueError('Invalid HF episode index')
            chunk=index//1000;stem=f'chunk-{chunk:03d}';filename=f'episode_{index:06d}'
            paths=dict(joints=f'data/{stem}/{filename}.parquet',**{a:f'videos/{stem}/observation.images.{a}/{filename}.mp4' for a in ('left','top','right')})
            for path in paths.values():_fetch(path,revision,True)
            manifest=json.loads(_fetch(f'episodes/{eid}.json',revision)[0])
            if manifest.get('samples_sha256')!=entry.get('samples_sha256') or manifest.get('rows')!=entry.get('rows'):
                raise ValueError('Episode manifest and registry disagree')
            base=f'https://huggingface.co/datasets/{REPO}/resolve/{revision}/'
            result=dict(status='ready',episode_id=eid,episode_index=index,commit=revision,
                rows=entry['rows'],valid_rows=entry.get('valid_rows'),capture_errors=entry.get('capture_errors'),missed_ticks=entry.get('missed_ticks'),
                viewer=f'https://huggingface.co/spaces/lerobot/visualize_dataset?path=%2Fandlyu%2FPublic-YAM-runs%2Fepisode_{index}',
                files={key:base+value for key,value in paths.items()},
                manifest=base+f'episodes/{eid}.json',message='Three camera streams and joint state/action data verified at one HF revision. Camera exposures are not hardware synchronized.')
    except Exception:
        result=dict(status='unavailable',episode_id=eid,message='HF publication could not be checked. Retry this lookup; the arms will not run again.')
    with _lock:_cache[eid]=(time.monotonic(),result,False)


def episode_status(eid):
    if not re.fullmatch(r'ep_[A-Za-z0-9_-]{1,80}',eid):raise ValueError('Choose a recorded source episode')
    with _lock:
        record=_cache.get(eid)
        if record and (record[2] or time.monotonic()-record[0]<20 or record[1]['status']=='ready'):
            return record[1]
        result=record[1] if record else dict(status='checking',episode_id=eid,message='Checking the full HF episode…')
        _cache[eid]=(time.monotonic(),result,True)
        threading.Thread(target=_resolve,args=(eid,),daemon=True).start()
        return result
