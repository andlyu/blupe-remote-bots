"""Read native EpisodeRecorder data without publishing it or contacting hosted history.

Only explicit episode roots are catalogued. Generated H.264 replays live in an
app-owned cache; neither arbitrary paths nor model logs become media routes.
"""
from collections import OrderedDict
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time

from .past_runs import run_result
from .run_history import recorded_model

EPISODE = re.compile(r'ep_[A-Za-z0-9_-]{1,100}')
MEDIA = re.compile(r'/api/native-runs/(ep_[A-Za-z0-9_-]{1,100})/([a-f0-9]{64})\.mp4')
ROLES = ('top', 'left', 'right', 'observer')
MAX_VIDEO_BYTES = 256 * 1024 * 1024
CACHE_BYTES = 1024 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_PATH = re.compile(r'images/(?:top|left|right|observer)-[0-9]{6,8}\.jpg')


class NativeFrames:
    """Read loose JPEGs or the recorder's uncompressed images.tar, never extract."""
    def __init__(self, folder, meta):
        self.folder = folder
        self.stack = ExitStack()
        self.archive = None
        self.members = {}
        try:
            if meta.get('recording_storage') == 'direct_usb_tar' or meta.get('images_archive'):
                if meta.get('images_archive') != 'images.tar':
                    raise ValueError('Unsupported native image archive')
                path = safe_file(folder/'images.tar', folder, 16*1024**3)
                descriptor = os.open(path, os.O_RDONLY|getattr(os, 'O_NOFOLLOW', 0))
                stream = self.stack.enter_context(os.fdopen(descriptor, 'rb'))
                self.archive = self.stack.enter_context(tarfile.open(fileobj=stream, mode='r:'))
                for index, member in enumerate(self.archive):
                    if index >= 288_000:
                        raise ValueError('Native archive exceeds replay limits')
                    if member.isdir() and member.name.rstrip('/') == 'images':
                        continue
                    if (not IMAGE_PATH.fullmatch(member.name) or not member.isfile()
                            or member.issparse() or not 0 < member.size <= MAX_IMAGE_BYTES
                            or member.name in self.members):
                        raise ValueError('Invalid native archive member')
                    self.members[member.name] = member
        except BaseException:
            self.stack.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def open(self, relative, role):
        if (not isinstance(relative, str) or not IMAGE_PATH.fullmatch(relative)
                or not relative.startswith('images/'+role+'-')):
            raise ValueError('Invalid native camera path')
        if self.archive is None:
            return safe_file(self.folder/relative, self.folder, MAX_IMAGE_BYTES).open('rb')
        member = self.members.get(relative)
        if member is None:
            raise ValueError('Native archive frame is missing')
        return self.archive.extractfile(member)


def safe_file(path, root, limit=None):
    """Reject symlink components below the explicitly configured root."""
    relative = path.relative_to(root)
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError('Native recording links are not served')
    if not current.is_file() or (limit is not None and current.stat().st_size > limit):
        raise ValueError('Native recording file is unavailable or too large')
    return current


def read_samples(folder):
    path = safe_file(folder / 'samples.jsonl', folder, 128 * 1024 * 1024)
    rows = []
    with path.open() as stream:
        for line in stream:
            if len(line) > 128_000 or len(rows) >= 72_000:
                raise ValueError('Native recording exceeds replay limits')
            row = json.loads(line)
            stamp = row.get('timestamp')
            if (not isinstance(stamp, (int,float)) or not math.isfinite(stamp)
                    or not 0 <= stamp <= 7200 or rows and stamp < rows[-1]['timestamp']):
                raise ValueError('Invalid native recording timestamps')
            rows.append(row)
    if not rows:
        raise ValueError('Native recording has no frames')
    return rows


def render_replay(folder, meta, target):
    """Bounded CPU encode. All recorded pauses are retained at the recorded FPS.

    This reads JPEGs only; it never imports a controller, enables motors or uploads.
    The existing playback helper supplies the fast preview and 1x Live speed from
    this same original-timing MP4, without a second expensive native encode.
    """
    from PIL import Image, ImageOps
    rows = read_samples(folder)
    samples = safe_file(folder/'samples.jsonl', folder)
    if meta.get('samples_sha256') and hashlib.sha256(samples.read_bytes()).hexdigest() != meta['samples_sha256']:
        raise ValueError('Finalized native samples changed')
    fps = meta.get('fps',10)
    if not isinstance(fps,(int,float)) or not math.isfinite(fps) or not 1 <= fps <= 30:
        raise ValueError('Unsupported recording frame rate')
    roles = [role for role in ROLES if rows[0].get(role+'_image_path')]
    if 'top' not in roles:
        raise ValueError('Native top-camera recording is missing')
    width,height = 640,432
    duration = rows[-1]['timestamp']-rows[0]['timestamp']+1/fps
    frames = max(1,math.ceil(duration*fps-1e-6))
    if frames > 72_000:
        raise ValueError('Native recording exceeds replay limits')
    with NativeFrames(folder, meta) as images, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo',
            '-pix_fmt','rgb24','-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0',
            '-an','-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p',
            '-movflags','+faststart','-fs',str(MAX_VIDEO_BYTES),'-y',str(target)],stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=errors)
        deadline = threading.Timer(600,process.kill)
        deadline.daemon = True; deadline.start()
        try:
            index = 0; image = None
            for number in range(frames):
                stamp = rows[0]['timestamp']+number/fps
                next_index = index
                while next_index+1 < len(rows) and rows[next_index+1]['timestamp'] <= stamp+1e-6:
                    next_index += 1
                if image is None or next_index != index:
                    index = next_index
                    canvas = Image.new('RGB',(width,height),(19,38,28))
                    main = 'observer' if 'observer' in roles else 'top'
                    tiles = [role for role in roles if role != main]
                    boxes = [(main,(0,0,640,320))]
                    tile_width = 640//max(1,len(tiles))
                    boxes += [(role,(i*tile_width,324,tile_width-2,108)) for i,role in enumerate(tiles)]
                    for role,(x,y,w,h) in boxes:
                        relative = rows[index].get(role+'_image_path')
                        if relative is None: continue
                        with images.open(relative,role) as frame, Image.open(frame) as source:
                            if source.width*source.height > 16_000_000:
                                raise ValueError('Native frame is too large')
                            tile = ImageOps.contain(source.convert('RGB'),(w,h))
                        canvas.paste(tile,(x+(w-tile.width)//2,y+(h-tile.height)//2))
                    image = canvas.tobytes()
                process.stdin.write(image)
            process.stdin.close()
            if process.wait(timeout=10) != 0:
                raise ValueError('Native replay encoding failed')
            if target.stat().st_size >= MAX_VIDEO_BYTES:
                raise ValueError('Native replay exceeded cache limits')
        finally:
            deadline.cancel()
            if process.poll() is None: process.kill()
            if process.stdin and not process.stdin.closed:
                try: process.stdin.close()
                except OSError: pass
            process.wait()
    return {'duration':frames/fps,'camera_order':roles,'video_layout':'observer-focus'}


class NativePastRuns:
    source = 'native'

    def __init__(self, roots, cache, *, robot_id='yam-1', model_reader=None, renderer=render_replay):
        self.roots = tuple(dict.fromkeys(Path(root).expanduser().resolve() for root in roots))
        if not self.roots or any(not root.is_dir() for root in self.roots):
            raise ValueError('Configure existing native episode roots')
        self.cache = Path(cache).expanduser().resolve()
        if any(self.cache == root or self.cache.is_relative_to(root) for root in self.roots):
            raise ValueError('Native media cache must be separate from source recordings')
        self.cache.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.cache.chmod(0o700)
        marker=self.cache/'.native-replay-cache'
        if not marker.exists():
            if any(self.cache.iterdir()): raise ValueError('Native media cache must be an empty app-owned directory')
            marker.write_text('native-history-v1\n')
        if marker.is_symlink() or marker.read_text() != 'native-history-v1\n':
            raise ValueError('Invalid native replay cache')
        self.robot_id = robot_id; self.model_reader = model_reader; self.renderer = renderer
        self.lock = threading.RLock(); self.updated = 0; self.rows = None; self.sources = {}
        self.jobs = {}; self.errors = OrderedDict(); self.queue = queue.Queue(maxsize=24)
        self.worker = None

    def _refresh(self):
        if self.rows is not None and time.monotonic()-self.updated < 2:
            return
        rows=[]; sources={}
        models=self.model_reader() if self.model_reader else {}
        for root in self.roots:
            for folder in root.glob('ep_*'):
                if not EPISODE.fullmatch(folder.name) or folder.is_symlink() or not folder.is_dir(): continue
                try:
                    raw=safe_file(folder/'manifest.json',root,1024*1024).read_bytes()
                    meta=json.loads(raw)
                    if not isinstance(meta,dict): continue
                    if meta.get('episode_id') != folder.name: continue
                    started=meta.get('started_at')
                    if not isinstance(started,(int,float)) or not math.isfinite(started): continue
                    if folder.name in sources: raise RuntimeError('Duplicate native episode ID in configured roots')
                    key=hashlib.sha256(str(folder).encode()+b'\0'+raw).hexdigest()
                    sources[folder.name]=(folder,meta,key)
                    rows.append(dict(episode_id=folder.name,episode_index=None,
                        robot_id=meta.get('robot_id') or self.robot_id,started_at=started,
                        prompt=str(meta.get('task') or 'Task not recorded'),
                        model=recorded_model(models.get(folder.name)) or recorded_model(meta.get('model')),
                        model_version=recorded_model(meta.get('model_version')),**run_result(meta)))
                except (OSError,ValueError,TypeError):
                    continue
        self.sources=sources; self.rows=sorted(rows,key=lambda r:r['started_at'],reverse=True)
        self.updated=time.monotonic()

    def page(self, offset=0, *, episode_id=None, episode_ids=None, robot_id=None, model='', query='', metadata=False, models=None):
        with self.lock:
            self._refresh(); available=[dict(row) for row in self.rows]
            if episode_id is not None: available=[r for r in available if r['episode_id']==episode_id]
            if episode_ids is not None: available=[r for r in available if r['episode_id'] in episode_ids]
            if robot_id is not None: available=[r for r in available if r['robot_id']==robot_id]
            choices=sorted({r['model'] or '__unrecorded__' for r in available},key=str.casefold)
            if model: available=[r for r in available if (r['model'] or '__unrecorded__')==model]
            if models: available=[r for r in available if (r['model'] or '__unrecorded__') in models]
            if query.strip() and episode_id is None:
                from .run_search import rank_runs
                available=rank_runs(available,query)
            selected=available if metadata else available[offset:offset+12]
            return dict(runs=selected if metadata else self._details(selected),total=len(available),models=choices,
                next_offset=None if metadata or offset+len(selected)>=len(available) else offset+len(selected),stale=False)

    def get(self, episode_id):
        # The termination receipt must see finalization immediately, so native
        # video preparation can overlap the existing five-second review window.
        with self.lock:
            self._refresh()
            source=self.sources.get(episode_id)
            if source:
                try:
                    raw=safe_file(source[0]/'manifest.json',source[0],1024*1024).read_bytes()
                    key=hashlib.sha256(str(source[0]).encode()+b'\0'+raw).hexdigest()
                    if key != source[2]: self.updated=0
                except (OSError,ValueError): self.updated=0
        rows=self.page(episode_id=episode_id)['runs']
        return rows[0] if rows else None

    def details_for(self, rows):
        with self.lock:
            self._refresh()
            return self._details(rows)

    def _details(self, rows):
        result=[]
        for row in rows:
            source=self.sources.get(row['episode_id'])
            if source is None: continue
            folder,meta,key=source
            detail=dict(row,video_url=None,original_video_url=None,original_available=False,
                compressed=False,camera_order=['top','left','right'],video_layout='observer-focus',video_duration_s=None)
            if meta.get('status') != 'finalized':
                detail['video_status']='unavailable'
            elif not meta.get('rows'):
                detail.update(video_status='empty',video_duration_s=0)
            else:
                target=self.cache/(key+'.mp4'); receipt=self.cache/(key+'.json')
                try:
                    info=json.loads(safe_file(receipt,self.cache,65536).read_text())
                    safe_file(target,self.cache)
                    if target.stat().st_size < 32: raise ValueError()
                    target.touch()
                    url=f'/api/native-runs/{row["episode_id"]}/{key}.mp4'
                    detail.update(video_status='ready',video_url=url,original_video_url=url,original_available=True,
                        camera_order=info['camera_order'],video_layout=info['video_layout'],video_duration_s=info['duration'])
                except (OSError,ValueError,KeyError):
                    if key in self.errors and time.monotonic()-self.errors[key]<60:
                        detail['video_status']='unavailable'
                    elif key in self.jobs:
                        detail['video_status']='processing'
                    else:
                        try:
                            self.queue.put_nowait((key,folder,meta))
                            self.jobs[key]=True; detail['video_status']='processing'
                            if self.worker is None or not self.worker.is_alive():
                                self.worker=threading.Thread(target=self._work,name='native-replay',daemon=True)
                                self.worker.start()
                        except queue.Full:
                            detail['video_status']='processing'
            result.append(detail)
        return result

    def _work(self):
        while True:
            try: key,folder,meta=self.queue.get(timeout=1)
            except queue.Empty:
                with self.lock:
                    if self.queue.empty(): self.worker=None; return
                continue
            # Candidates may overlap. A process that loses the encode lock must
            # never unlink the other process's active temporary output.
            descriptor,name=tempfile.mkstemp(prefix=key+'.',suffix='.tmp.mp4',dir=self.cache)
            os.close(descriptor)
            temporary=Path(name)
            try:
                self._encode(key,folder,meta,temporary)
            except BlockingIOError:
                pass  # Another native app is encoding; a later detail poll retries.
            except Exception:
                with self.lock:
                    self.errors[key]=time.monotonic()
                    while len(self.errors)>128: self.errors.popitem(last=False)
            finally:
                temporary.unlink(missing_ok=True)
                with self.lock: self.jobs.pop(key,None)
                self.queue.task_done()

    def _encode(self,key,folder,meta,temporary):
        import fcntl
        descriptor=os.open(self.cache/'.encode.lock',os.O_WRONLY|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(descriptor,'w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            # A previous process may have completed while this request queued.
            if (self.cache/(key+'.mp4')).is_file() and (self.cache/(key+'.json')).is_file(): return
            self._prune()
            if shutil.disk_usage(self.cache).free < MAX_VIDEO_BYTES + 256*1024*1024:
                raise ValueError('Not enough native cache space')
            info=self.renderer(folder,meta,temporary)
            if not temporary.is_file() or temporary.stat().st_size < 32: raise ValueError()
            temporary.replace(self.cache/(key+'.mp4'))
            receipt=self.cache/(key+'.json')
            temp_receipt=receipt.with_suffix('.json.tmp')
            temp_receipt.write_text(json.dumps(info)); temp_receipt.replace(receipt)
            self._prune()

    def _prune(self):
        # Only reproducible files in the marked app cache can be evicted. Native
        # episode roots and the model logs/assessment databases are never touched.
        files=[p for p in self.cache.glob('*.mp4') if re.fullmatch(r'[a-f0-9]{64}\.mp4',p.name) and not p.is_symlink()]
        total=sum(p.stat().st_size for p in files)
        for path in sorted(files,key=lambda p:p.stat().st_mtime):
            if total <= CACHE_BYTES: break
            total-=path.stat().st_size
            path.unlink(); path.with_suffix('.json').unlink(missing_ok=True)

    def media_path(self, episode_id, key):
        with self.lock:
            self._refresh()
            source=self.sources.get(episode_id)
            if source is None or source[2] != key: raise ValueError('Unknown native replay')
            return safe_file(self.cache/(key+'.mp4'),self.cache)
