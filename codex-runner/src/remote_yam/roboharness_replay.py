"""Public, timestamped top-camera clips; independent of control and model inputs.

Reads only the configured BluPe camera. It creates no session or motor command.
Temporary frames are removed after encoding; immutable public MP4/metadata remain.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
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


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='milliseconds')


class PublicCameraReplay:
    def __init__(self, root, *, robot_id, origin=API):
        if origin != API or robot_id not in ROBOTS:
            raise ValueError('Public replay requires a registered BluPe station and fixed camera origin')
        self.root = Path(root).resolve()
        self.robot_id = robot_id
        self.source = CameraFrameSource(API, timeout_s=1, camera_names=('top',))
        self.url = API + '/v1/robots/' + robot_id + '/cameras/top.jpg'

    def ready(self):
        return bool(shutil.which('ffmpeg'))

    def start(self, controller):
        attempt = controller.status().get('attempt_id')
        thread = threading.Thread(target=self.follow, args=(controller, attempt), daemon=True,
                                  name='roboharness-public-camera-replay')
        thread.start()
        return thread

    def follow(self, controller, attempt, *, clock=time.time, sleep=time.sleep):
        episode = None

        def event(kind, message, **details):
            state = controller.status()
            if state.get('attempt_id') == attempt:
                controller._interactions.add(kind, message, **details)

        try:
            if not self.ready():
                raise RuntimeError('Video encoder unavailable')
            self.root.mkdir(parents=True, exist_ok=True)
            if sum(p.stat().st_size for p in self.root.rglob('*.mp4')) > 1024 * 1024 * 1024:
                raise RuntimeError('Public replay storage is full')
            wait_until = clock() + 3600
            while clock() < wait_until:
                state = controller.status()
                if state.get('attempt_id') != attempt:
                    return
                if state['status'] == 'running' and EPISODE.fullmatch(state.get('episode_id') or ''):
                    episode = state['episode_id']
                    break
                if state['status'] not in {'queued', 'preparing'}:
                    return
                sleep(.2)
            if episode is None:
                raise RuntimeError('Queue wait exceeded replay preparation limit')
            event('replay_capture', 'Recording actual overhead camera footage for this run')
            with tempfile.TemporaryDirectory(prefix='.capture-', dir=self.root) as work:
                work = Path(work)
                frames = []
                deadline = clock() + 610
                partial = False
                while clock() < deadline:
                    state = controller.status()
                    if (state.get('attempt_id') != attempt or state.get('episode_id') != episode
                            or state['status'] != 'running'):
                        break
                    tick = clock()
                    frame = None
                    try:
                        candidate = self.source.fetch('top', self.url)
                        if candidate.name != 'top':raise ValueError('Unexpected camera role')
                        stamp = candidate.source_captured_at
                        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                                or not 0 <= clock() - stamp <= 2):
                            raise ValueError('No fresh source timestamp')
                        frame = candidate
                    except Exception:
                        partial = True
                    received = clock()
                    name = f'{len(frames):06d}.jpg'
                    self.draw(frame, received).save(work / name, format='JPEG', quality=85)
                    frames.append(dict(file=name, received_at=received,
                        source_captured_at=frame.source_captured_at if frame else None,
                        actual_image=frame is not None))
                    if len(frames) >= 1220:
                        partial = True
                        break
                    sleep(max(0, .5 - (clock() - tick)))
                if not frames or not any(f['actual_image'] for f in frames):
                    raise RuntimeError('No actual camera frames captured')
                partial |= any(b['received_at'] - a['received_at'] > 1.5 for a, b in zip(frames, frames[1:]))
                event('replay_encoding', 'Camera capture finished; preparing retained playback')
                metadata = self.publish(work, episode, frames, partial=partial,
                    started_at=state.get('run_started_at'), ended_at=clock())
                event('replay_ready', 'Retained physical camera replay is ready' + ('; capture has gaps' if partial else ''),
                      episode_id=episode, video_sha256=metadata['preview']['sha256'], partial=partial)
        except Exception as exc:
            # Fixed diagnostic only: no paths, exception bodies, identities or capabilities.
            event('replay_failed', 'Retained camera replay could not be prepared. Check the normal archive later.',
                  episode_id=episode, cause_type=type(exc).__name__)

    @staticmethod
    def draw(frame, received):
        canvas = Image.new('RGB', (640, 520), '#10151b')
        draw = ImageDraw.Draw(canvas)
        if frame is not None:
            with Image.open(io.BytesIO(frame.jpeg)) as image:
                if image.format != 'JPEG' or image.width * image.height > 1920 * 1080:
                    raise ValueError('Invalid bounded camera image')
                image = image.convert('RGB')
                image.thumbnail((640, 480))
                canvas.paste(image, ((640 - image.width) // 2, (480 - image.height) // 2))
            label = 'ACTUAL TOP CAMERA / source ' + utc(frame.source_captured_at)
        else:
            label = 'NO FRESH CAMERA FRAME / gap retained'
            draw.text((20, 220), 'Camera unavailable', fill='white')
        draw.text((8, 484), label, fill='white')
        draw.text((8, 501), 'Received ' + utc(received), fill='white')
        return canvas

    def publish(self, work, episode, frames, *, partial, started_at, ended_at):
        if not EPISODE.fullmatch(episode):
            raise ValueError('Invalid episode')
        rows = ['ffconcat version 1.0']
        for i, frame in enumerate(frames):
            rows.append("file '" + frame['file'] + "'")
            duration = frames[i + 1]['received_at'] - frame['received_at'] if i + 1 < len(frames) else .5
            if not math.isfinite(duration) or not 0 < duration < 30:
                raise ValueError('Invalid camera timeline')
            rows.append('duration ' + str(duration))
        rows.append("file '" + frames[-1]['file'] + "'")
        (work / 'frames.ffconcat').write_text('\n'.join(rows) + '\n')
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '1',
            '-i', 'frames.ffconcat', '-fps_mode', 'vfr', '-c:v', 'libx264', '-threads', '1',
            '-preset', 'fast', '-crf', '24', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', 'clip.mp4'],
            cwd=work, check=True, timeout=30, capture_output=True, stdin=subprocess.DEVNULL)
        data = (work / 'clip.mp4').read_bytes()
        if not 0 < len(data) <= MAX_VIDEO_BYTES:
            raise ValueError('Encoded replay exceeds public media limit')
        digest = hashlib.sha256(data).hexdigest()
        folder = self.root / episode
        folder.mkdir(exist_ok=True)
        target = folder / (digest + '.mp4')
        if target.exists():
            if target.stat().st_size!=len(data) or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
                raise ValueError('Existing immutable replay differs')
        else:
            (work / 'clip.mp4').replace(target)
        metadata = dict(episode_id=episode, robot_id=self.robot_id, model='RoboHarness', bytes=len(data),
            started_at=started_at, ended_at=ended_at, locally_ready_at=time.time(), original_available=False,
            capture_source='public_top_camera', capture_partial=bool(partial), frames=frames,
            encoder_version=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            preview=dict(sha256=digest, duration_s=frames[-1]['received_at'] - frames[0]['received_at'] + .5,
                         speed=1, camera_order=['top'], layout='top_camera_with_source_utc'))
        temporary = work / 'metadata.json'
        temporary.write_text(json.dumps(metadata, indent=2) + '\n')
        temporary.replace(self.root / (episode + '.json'))
        return metadata
