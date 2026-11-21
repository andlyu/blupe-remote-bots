"""Immediate retained camera playback; never participates in robot control."""
import json
import time
import math
import threading
from dataclasses import dataclass
from urllib.request import Request,build_opener
from pathlib import Path
from remote_yam.cameras import CameraFrameSource,NoRedirect
from camera_replay import PublicCameraReplay, API


@dataclass(frozen=True)
class CameraSample:
    name:str
    jpeg:bytes
    received_at:float
    source_captured_at:float|None


class ClockedCamera(CameraFrameSource):
    def _capture_one(self,name,url):
        # The configured public .jpg relay supplies bounded JPEG responses and
        # X-Captured-At. Keep this recorder independent of shared reader changes.
        request=Request(url,headers={'Accept':'image/jpeg','Cache-Control':'no-cache'})
        with build_opener(NoRedirect).open(request,timeout=self.timeout_s) as response:
            headers=response.headers
            lengths=headers.get_all('Content-Length',[])
            if headers.get_content_type()!='image/jpeg' or len(lengths)!=1 or not str(lengths[0]).isdigit():raise ValueError('Timestamped JPEG headers unavailable')
            size=int(lengths[0])
            if not 4<=size<=2*1024*1024:raise ValueError('Timestamped JPEG exceeds limit')
            deadline=time.monotonic()+self.timeout_s;data=bytearray()
            while len(data)<size:
                if time.monotonic()>deadline:raise TimeoutError('Timestamped JPEG deadline exceeded')
                chunk=response.read1(min(65536,size-len(data)))
                if not chunk:raise ValueError('Timestamped JPEG incomplete')
                data.extend(chunk)
            if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):raise ValueError('Timestamped JPEG invalid')
            stamp=float(headers.get('X-Captured-At','nan'))
            if not math.isfinite(stamp) or stamp<=0:raise ValueError('Camera source timestamp unavailable')
            return CameraSample(name,bytes(data),time.time(),stamp)

    def fetch(self, name, url):
        frame=super().fetch(name,url)
        stamp=frame.source_captured_at
        if type(stamp) in (float,int):
            ahead=stamp-time.time()
            if 0<ahead<=.5:time.sleep(ahead+.002)
        return frame


class KinexReplay(PublicCameraReplay):
    def __init__(self,root,*,robot_id,upload):
        super().__init__(root,robot_id=robot_id)
        self.source=ClockedCamera(API,timeout_s=1,camera_names=('top',))
        self.upload=upload;self.phase='waiting_for_episode';self.result=None
        self.controller=None;self.attempt=None;self._closed=False
        self._publication_allowed=threading.Event()

    def start(self,controller):
        self.controller=controller;self.attempt=controller.status().get('attempt_id')
        owner=self
        class Journal:
            def add(self,kind,message,**details):
                stages={'replay_capture':'capturing','replay_encoding':'encoding','replay_ready':'ready','replay_failed':'failed'}
                if kind in stages:owner.phase=stages[kind]
                controller._interactions.add(kind,message,**details)
        class RecordingView:
            _interactions=Journal()
            def status(self):
                state=controller.status()
                if owner._closed:state=dict(state,status='stopped')
                return state
        return super().start(RecordingView())

    def close(self):self._closed=True

    def allow_publish(self):self._publication_allowed.set()

    def publish(self,work,episode,frames,*,partial,started_at,ended_at):
        deadline=time.monotonic()+15
        while not self._publication_allowed.wait(.1):
            if self._closed or time.monotonic()>deadline:raise RuntimeError('Terminal website status not confirmed; recording withheld')
        if self._closed:raise RuntimeError('Recording finalization cancelled')
        state=self.controller.status()
        if state.get('attempt_id')!=self.attempt or state.get('episode_id')!=episode or not state.get('session_id'):
            raise RuntimeError('Camera recording no longer matches its controller attempt')
        meta=super().publish(work,episode,frames,partial=partial,started_at=started_at,ended_at=ended_at)
        meta.update(model='Kinex',session_id=state['session_id'],capture_fps=2)
        # The encoder writes locally before returning; these files are not
        # served publicly until this Kinex attribution and matching upload pass.
        path=self.root/episode/(meta['preview']['sha256']+'.mp4')
        temporary=self.root/(episode+'.kinex.tmp');temporary.write_text(json.dumps(meta,indent=2)+'\n')
        temporary.replace(self.root/(episode+'.json'))
        self.phase='uploading'
        self.result=self.upload(meta,path)
        return meta
