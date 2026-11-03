"""Overhead paired RGB-D plus wrist RGB; no unused wrist-depth transfer.

Only overhead points are measured in robot coordinates. Every view has an
explicit source timestamp, must follow settled feedback, and stays <=2s old.
The normal read-only whole-set recovery/cancellation behavior is inherited.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import time
from urllib import error
from urllib.parse import quote

from .api_depth import StaleDepth,NoDepthImage,depth_robot_stopped
from .api_depth_set import ApiDepthSet,PairedDepthFrame
from .cameras import CameraFrameSource,CameraUnavailable


class RoboHarnessCameras(ApiDepthSet):
    def __init__(self,origin,*,robot_id):
        super().__init__(origin,origin,robot_id=robot_id)
        self.wrist_rgb=CameraFrameSource(origin,camera_names=('left','right'))
        self._rgb_root=origin.rstrip('/')+'/v1/robots/'+quote(robot_id,safe='')+'/cameras/'

    def capture(self,observation,*,stopped=None):
        self.snapshots={}
        if observation.get('robot_id',observation.get('jetson_id',self.robot_id))!=self.robot_id:
            raise ValueError('Camera observation belongs to another robot')
        try:report=json.loads(self.apis['top'].read('/calibration',256000))
        except error.HTTPError as exc:
            raise CameraUnavailable('top','Calibration read failed',exc.code,exc.code in (408,429,500,502,503,504)) from None
        if stopped is None:stopped=depth_robot_stopped(observation)
        with ThreadPoolExecutor(max_workers=3) as pool:
            depth=pool.submit(self.apis['top'].capture,report=report,cancelled=self._cancelled,stopped=stopped)
            wrists={role:pool.submit(self.wrist_rgb.fetch,role,self._rgb_root+role+'.jpg') for role in ('left','right')}
            try:snapshot=depth.result()
            except NoDepthImage:raise
            except (StaleDepth,TimeoutError,ConnectionError,error.HTTPError,RuntimeError) as exc:
                raise CameraUnavailable('top','Fresh paired overhead RGB-D unavailable') from exc
            rgb=[wrists[role].result() for role in ('left','right')]
        self.require_post_settle({'top':snapshot},observation)
        frames=[PairedDepthFrame('top',snapshot.image(),time.time(),snapshot.metadata['captured_at'],
            snapshot.metadata['sensor_serial'],snapshot.metadata['calibration_id'],source_captured_at=snapshot.metadata['captured_at']),*rgb]
        for frame in frames:
            stamp=frame.source_captured_at
            if type(stamp) not in (int,float) or not math.isfinite(stamp):
                raise CameraUnavailable(frame.name,'Source capture timestamp is missing',retryable=False)
            if not 0<=time.time()-stamp<=2:
                raise CameraUnavailable(frame.name,'Source image is older than 2 seconds')
            if observation.get('source')=='hardware' and depth_robot_stopped(observation) and stamp<=observation['observed_at']:
                raise CameraUnavailable(frame.name,'Image precedes settled feedback')
        if not 0<=snapshot.age()<=2:raise CameraUnavailable('top','Paired depth aged while assembling views')
        if self._cancelled():raise RuntimeError('Camera capture cancelled')
        self.snapshots={'top':snapshot}
        return frames
