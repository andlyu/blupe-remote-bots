"""Read verified same-host replay cache; never wait on a remote dataset catalog."""
import hashlib
import json
import os
from pathlib import Path
import re


class QuickReplays:
    def __init__(self, root=None):
        self.root=Path(root or os.environ['YAM_LOCAL_REPLAY_ROOT']).resolve() if (root or os.environ.get('YAM_LOCAL_REPLAY_ROOT')) else None

    def get(self, eid, robot_id=None):
        if self.root is None or not re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',eid or ''):
            return None
        try:
            meta=json.loads((self.root/(eid+'.json')).read_text())
            info=meta['preview'];digest=info['sha256']
            if (meta['episode_id']!=eid or not re.fullmatch(r'[0-9a-f]{64}',digest)
                    or robot_id is not None and meta['robot_id']!=robot_id):
                return None
            path=self.root/eid/(digest+'.mp4')
            if (not 0<path.stat().st_size<=16*1024*1024 or path.stat().st_size!=meta['bytes']
                    or path.resolve().parent!=self.root/eid):
                return None
            # Installation verifies the hash before atomic publication. Immutable
            # names avoid returning mixed metadata or changing a playing video.
            from remote_yam.past_runs import run_result
            return dict(episode_id=eid,episode_index=None,robot_id=meta['robot_id'],
                started_at=meta.get('started_at'),prompt=meta.get('task') or 'Task unavailable',
                **run_result(meta),video_url=f'/api/quick-replays/{eid}/{digest}.mp4',
                original_video_url=f'https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/videos/{eid}.mp4',
                original_available=meta.get('original_available',False),compressed=True,
                video_duration_s=info['duration_s'],preview_speed=10,
                video_layout=info.get('layout'),camera_order=info['camera_order'],
                video_quality=info.get('quality_stage','final'),video_sha256=digest,
                recording_ended_at=meta.get('ended_at'),locally_ready_at=meta['locally_ready_at'])
        except (OSError,ValueError,KeyError,TypeError):
            return None

    def video(self,eid,digest,range_header=None):
        if (self.root is None or not re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',eid)
                or not re.fullmatch(r'[0-9a-f]{64}',digest)):
            return None
        path=self.root/eid/(digest+'.mp4')
        if path.resolve().parent!=self.root/eid:
            return None
        try:
            body=path.read_bytes()
        except OSError:
            return None
        if not 0<len(body)<=16*1024*1024 or hashlib.sha256(body).hexdigest()!=digest:
            return None
        headers=[(b'accept-ranges',b'bytes'),(b'etag',('"'+digest+'"').encode())]
        if range_header:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header)
            if not match or not any(match.groups()):
                return 416,b'',headers+[(b'content-range',f'bytes */{len(body)}'.encode())]
            first,last=match.groups()
            start=int(first) if first else max(0,len(body)-int(last))
            end=min(int(last),len(body)-1) if first and last else len(body)-1
            if start>=len(body) or start>end:
                return 416,b'',headers+[(b'content-range',f'bytes */{len(body)}'.encode())]
            headers.append((b'content-range',f'bytes {start}-{end}/{len(body)}'.encode()))
            return 206,body[start:end+1],headers
        return 200,body,headers
