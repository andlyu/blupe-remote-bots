"""Timestamped public camera clips, encoded while the physical run is active.

Only fixed public camera reads. Failed encodes retain bounded JPEGs and a recovery
manifest; recovery never creates a session, reads a camera or sends a movement.
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import tempfile
import threading
import time
from PIL import Image, ImageDraw
from .cameras import CameraFrameSource

API = 'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com'
ROBOTS = {'yam-1', 'robot-ba8413962083809c'}
EPISODE = re.compile(r'ep_[A-Za-z0-9_-]{1,100}')
MAX_VIDEO_BYTES = 16 * 1024 * 1024
MAX_STORAGE_BYTES = 1024 * 1024 * 1024
PERIOD = .5


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='milliseconds')


class StreamingCameraEncoder:
    """Bounded stdin writes keep a stalled encoder off the capture/control path."""
    def __init__(self, work):
        self.work=Path(work)
        self.errors=(self.work/'encoder.log').open('wb')
        try:
            self.process=subprocess.Popen(['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                '-f','image2pipe','-framerate','2','-c:v','mjpeg','-i','pipe:0',
                '-c:v','libx264','-threads','1','-preset','fast','-crf','24',
                '-pix_fmt','yuv420p','-movflags','+faststart','-f','mp4','clip.partial'],
                cwd=self.work,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.errors)
            os.set_blocking(self.process.stdin.fileno(),False)
        except Exception:
            if hasattr(self,'process'):
                self.process.kill();self.process.wait(timeout=2);self.process.stdin.close()
            self.errors.close()
            raise

    def write(self,data):
        view=memoryview(data);deadline=time.monotonic()+1
        fd=self.process.stdin.fileno()
        while view:
            if self.process.poll() is not None:raise RuntimeError('Camera encoder exited')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Camera encoder write deadline exceeded')
            if not select.select([], [fd], [], min(.05,remaining))[1]:continue
            try:written=os.write(fd,view)
            except BlockingIOError:continue
            view=view[written:]

    def finish(self):
        self.process.stdin.close()
        try:
            if self.process.wait(timeout=10)!=0:raise RuntimeError('Camera encoder failed')
        finally:self.errors.close()

    def abort(self):
        if self.process.poll() is None:self.process.kill()
        try:self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
        try:self.process.stdin.close()
        except (OSError,ValueError):pass
        self.errors.close()


class PublicCameraReplay:
    def __init__(self,root,*,robot_id,origin=API):
        if origin!=API or robot_id not in ROBOTS:
            raise ValueError('Public replay requires a registered BluPe station and fixed camera origin')
        self.root=Path(root).resolve();self.robot_id=robot_id
        self.source=CameraFrameSource(API,timeout_s=1,camera_names=('top',))
        self.url=API+'/v1/robots/'+robot_id+'/cameras/top.jpg'

    def ready(self):return bool(shutil.which('ffmpeg'))

    def start(self,controller):
        attempt=controller.status().get('attempt_id')
        thread=threading.Thread(target=self.follow,args=(controller,attempt),daemon=True,
            name='roboharness-public-camera-replay')
        thread.start();return thread

    def _storage_size(self):
        total=0
        for path in self.root.rglob('*'):
            try:
                if path.is_file():total+=path.stat().st_size
            except FileNotFoundError:continue
        return total

    @staticmethod
    def _save_manifest(work,job):
        temporary=work/'capture.next'
        temporary.write_text(json.dumps(job,indent=2)+'\n')
        temporary.replace(work/'capture.json')

    def follow(self,controller,attempt,*,clock=time.time,sleep=time.sleep):
        episode=None;encoder=None;work=None;capture_lock=None
        def event(kind,message,**details):
            if controller.status().get('attempt_id')==attempt:
                controller._interactions.add(kind,message,**details)
        try:
            if not self.ready():raise RuntimeError('Video encoder unavailable')
            self.root.mkdir(parents=True,exist_ok=True)
            if self._storage_size()>MAX_STORAGE_BYTES:raise RuntimeError('Public replay storage is full')
            deadline=clock()+3600
            while clock()<deadline:
                state=controller.status()
                if state.get('attempt_id')!=attempt:return
                if state['status']=='running' and EPISODE.fullmatch(state.get('episode_id') or ''):
                    episode=state['episode_id'];break
                if state['status'] not in {'queued','preparing'}:return
                sleep(.2)
            if episode is None:raise RuntimeError('Queue wait exceeded replay preparation limit')
            work=Path(tempfile.mkdtemp(prefix='.pending-',dir=self.root))
            capture_lock=(work/'.encode-lock').open('a+b')
            fcntl.flock(capture_lock,fcntl.LOCK_EX)
            job=dict(capture_status='capturing',episode_id=episode,robot_id=self.robot_id,model='RoboHarness',
                started_at=state.get('run_started_at'),ended_at=None,partial=False,frames=[])
            self._save_manifest(work,job)
            event('replay_capture','Recording actual overhead footage and preparing playback during this run')
            encoder=StreamingCameraEncoder(work)
            origin=None;previous=None;capture_number=0;last_rendered=None
            def flush(until,*,inclusive=True):
                nonlocal encoder,last_rendered
                while previous is not None and len(job['frames'])<1220:
                    stamp=origin+len(job['frames'])*PERIOD
                    if stamp>until or not inclusive and stamp>=until-1e-6:break
                    frame,received,number=previous
                    if frame is not None and not 0<=stamp-frame.source_captured_at<=2:
                        frame=None;job['partial']=True
                    name=f"{len(job['frames']):06d}.jpg"
                    buffer=io.BytesIO();self.draw(frame,received,presented_at=stamp).save(buffer,format='JPEG',quality=85)
                    image_bytes=buffer.getvalue()
                    if self._storage_size()+len(image_bytes)>MAX_STORAGE_BYTES:raise RuntimeError('Public replay storage is full')
                    (work/name).write_bytes(image_bytes)
                    row=dict(file=name,video_at=stamp,received_at=received,
                        source_captured_at=frame.source_captured_at if frame else None,
                        actual_image=frame is not None,presentation_hold=number==last_rendered)
                    job['frames'].append(row);last_rendered=number
                    self._save_manifest(work,job)
                    if encoder is not None:
                        try:encoder.write(image_bytes)
                        except Exception as exc:
                            encoder.abort();encoder=None
                            job['encoder_error_type']=type(exc).__name__
                    if len(job['frames'])%100==0 and self._storage_size()>MAX_STORAGE_BYTES:
                        raise RuntimeError('Public replay storage is full')
            deadline=clock()+610
            while clock()<deadline:
                state=controller.status()
                if state.get('attempt_id')!=attempt or state.get('episode_id')!=episode or state['status']!='running':break
                tick=clock();frame=None
                try:
                    candidate=self.source.fetch('top',self.url);stamp=candidate.source_captured_at
                    if candidate.name!='top' or type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=clock()-stamp<=2:
                        raise ValueError('No fresh bounded source timestamp')
                    frame=candidate
                except Exception:job['partial']=True
                received=clock()
                if origin is None:origin=received
                flush(received,inclusive=False)
                previous=(frame,received,capture_number);capture_number+=1
                flush(received)
                if len(job['frames'])>=1220:
                    job['partial']=True;break
                sleep(max(0,PERIOD-(clock()-tick)))
            flush(clock())
            job['partial'] |= clock()>=deadline
            job['ended_at']=clock();job['capture_status']='finished'
            self._save_manifest(work,job)
            if not job['frames'] or not any(f['actual_image'] for f in job['frames']):raise RuntimeError('No actual camera frames captured')
            event('replay_encoding','Camera capture finished; finalizing retained playback')
            streamed=False
            if encoder is not None:
                try:encoder.finish();streamed=True
                finally:encoder.abort();encoder=None
            metadata=self.publish(work,episode,job['frames'],partial=job['partial'],
                started_at=job['started_at'],ended_at=job['ended_at'],encoded=streamed)
            shutil.rmtree(work);work=None
            event('replay_ready','Retained physical camera replay is ready'+('; capture has gaps' if job['partial'] else ''),
                episode_id=episode,video_sha256=metadata['preview']['sha256'],partial=job['partial'])
        except Exception as exc:
            if encoder is not None:encoder.abort()
            if work is not None and (work/'capture.json').exists():
                if job.get('capture_status')!='finished':job['capture_status']='interrupted'
                job['preparation_status']='retained_for_recovery';job['preparation_error_type']=type(exc).__name__
                self._save_manifest(work,job)
            event('replay_failed','Replay preparation failed; captured frames are retained for recovery. Check the archive or refresh later.',
                episode_id=episode,cause_type=type(exc).__name__)
        finally:
            if capture_lock is not None:capture_lock.close()

    @staticmethod
    def draw(frame,received,*,presented_at=None):
        canvas=Image.new('RGB',(640,520),'#10151b');draw=ImageDraw.Draw(canvas)
        if frame is not None:
            with Image.open(io.BytesIO(frame.jpeg)) as image:
                if image.format!='JPEG' or image.width*image.height>1920*1080:raise ValueError('Invalid bounded camera image')
                image=image.convert('RGB');image.thumbnail((640,480));canvas.paste(image,((640-image.width)//2,(480-image.height)//2))
            label='ACTUAL TOP CAMERA / source '+utc(frame.source_captured_at)
        else:
            label='NO FRESH CAMERA FRAME / gap retained';draw.text((20,220),'Camera unavailable',fill='white')
        draw.text((8,484),label,fill='white')
        label='Received '+utc(received)
        if presented_at is not None:label+=' / timeline '+utc(presented_at)
        draw.text((8,501),label,fill='white');return canvas

    def publish(self,work,episode,frames,*,partial,started_at,ended_at,encoded=False):
        if not EPISODE.fullmatch(episode):raise ValueError('Invalid episode')
        work=Path(work)
        if not encoded:
            rows=['ffconcat version 1.0']
            for i,frame in enumerate(frames):
                if not re.fullmatch(r'[0-9]{6}\.jpg',frame['file']):raise ValueError('Invalid recovery frame path')
                stamp=frame.get('video_at',frame['received_at'])
                end=frames[i+1].get('video_at',frames[i+1]['received_at']) if i+1<len(frames) else stamp+PERIOD
                duration=end-stamp
                if not math.isfinite(duration) or not 0<duration<30:raise ValueError('Invalid camera timeline')
                rows.extend(["file '"+frame['file']+"'",'duration '+str(duration)])
            rows.append("file '"+frames[-1]['file']+"'")
            (work/'frames.ffconcat').write_text('\n'.join(rows)+'\n')
            subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','1',
                '-i','frames.ffconcat','-fps_mode','vfr','-c:v','libx264','-threads','1','-preset','fast','-crf','24',
                '-pix_fmt','yuv420p','-movflags','+faststart','-f','mp4','clip.partial'],cwd=work,check=True,
                timeout=max(30,min(240,10+len(frames)*.25)),capture_output=True,stdin=subprocess.DEVNULL)
        data=(work/'clip.partial').read_bytes()
        if not 0<len(data)<=MAX_VIDEO_BYTES:raise ValueError('Encoded replay exceeds public media limit')
        digest=hashlib.sha256(data).hexdigest();folder=self.root/episode;folder.mkdir(exist_ok=True)
        target=folder/(digest+'.mp4')
        if target.exists():
            if target.stat().st_size!=len(data) or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Existing immutable replay differs')
        else:(work/'clip.partial').replace(target)
        first=frames[0].get('video_at',frames[0]['received_at']);last=frames[-1].get('video_at',frames[-1]['received_at'])
        metadata=dict(episode_id=episode,robot_id=self.robot_id,model='RoboHarness',bytes=len(data),
            started_at=started_at,ended_at=ended_at,locally_ready_at=time.time(),original_available=False,
            capture_source='public_top_camera',capture_partial=bool(partial),frames=frames,
            presentation='2Hz wall-clock slots; original source and receive UTC retained; holds are labelled in metadata',
            encoder_version=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            preview=dict(sha256=digest,duration_s=last-first+PERIOD,speed=1,camera_order=['top'],
                layout='top_camera_with_source_utc',encoder_mode='streaming' if encoded else 'recovered_batch'))
        temporary=work/'metadata.next';temporary.write_text(json.dumps(metadata,indent=2)+'\n')
        temporary.replace(self.root/(episode+'.json'));return metadata

    def recover_pending(self):
        """Prepare only existing captured frames; no camera/session/motor access."""
        recovered=[]
        for work in sorted(self.root.glob('.pending-*')):
            lock=None
            try:
                if work.is_symlink() or work.resolve().parent!=self.root:continue
                lock=(work/'.encode-lock').open('a+b')
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:continue
                path=work/'capture.json'
                if path.is_symlink():continue
                if path.stat().st_size>1024*1024:continue
                job=json.loads(path.read_text());episode=job.get('episode_id')
                if job.get('robot_id')!=self.robot_id or job.get('model')!='RoboHarness' or not EPISODE.fullmatch(episode or ''):continue
                if not 1<=len(job.get('frames',[]))<=1220:continue
                for frame in job['frames']:
                    if not re.fullmatch(r'[0-9]{6}\.jpg',frame['file']) or (work/frame['file']).is_symlink():raise ValueError('Invalid recovery frame')
                meta=self.publish(work,episode,job['frames'],partial=job.get('partial',True) or job.get('capture_status')!='finished',
                    started_at=job.get('started_at'),ended_at=job.get('ended_at'))
                shutil.rmtree(work);recovered.append(meta['episode_id'])
            except Exception:continue
            finally:
                if lock is not None:lock.close()
        return recovered
