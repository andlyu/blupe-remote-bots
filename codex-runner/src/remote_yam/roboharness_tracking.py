"""Persistent image points, bidirectional optical flow and calibrated depth.

Tracking uses the run's explicitly selected paired camera. Coordinates returned for actuation are
fresh shared RGB-D measurements in the explicitly calibrated arm-base frames.
Lost/occluded points never become guessed robot targets.
"""
import re
import cv2
import numpy as np

from .roboharness_control import InputRejected, number


class StaleTrackingDepth(InputRejected):
    """Only a read-only capture may be reacquired; no movement has been sent."""


class KeypointTracker:
    def __init__(self, camera='top'):
        if camera not in ('top','left','right'):raise InputRejected('Select a registered grounding camera')
        self.camera=camera
        self.snapshot=None;self.points={};self.errors={};self._gray=None

    def _registered_pixel(self, point_id, u, v):
        if self.snapshot is None:raise InputRejected('Capture paired RGB-D before selecting a point')
        if not isinstance(point_id,str) or not re.fullmatch(r'point_(?:[0-9]|1[0-5])',point_id):
            raise InputRejected('Point ID must be point_0 through point_15')
        u=number(u,'normalized u',0,1000);v=number(v,'normalized v',0,1000)
        h,w=self.snapshot.rgb.shape[:2]
        # 1000 names the last pixel, rather than an out-of-bounds image edge.
        return np.array([u*(w-1)/1000,v*(h-1)/1000],dtype=np.float32)

    def register(self, point_id, u, v):
        self.points[point_id]=self._registered_pixel(point_id,u,v)
        self.errors.pop(point_id,None)

    def register_many(self, registrations):
        if not isinstance(registrations,list) or not 1<=len(registrations)<=3:
            raise InputRejected('Inspect one to three points from the same image')
        staged={}
        for item in registrations:
            if not isinstance(item,dict) or set(item)!={'point_id','u','v'}:
                raise InputRejected('Inspection requires a point ID and both image coordinates')
            point_id=item['point_id']
            pixel=self._registered_pixel(point_id,item['u'],item['v'])
            if point_id in staged:raise InputRejected('Inspection point IDs must be distinct')
            staged[point_id]=pixel
        # Validate the complete batch before changing any selected point/error.
        # Every pixel refers to this existing model-view snapshot; update/measure
        # still require fresh paired depth and current registered camera poses.
        self.points.update(staged)
        for point_id in staged:self.errors.pop(point_id,None)

    def update(self,snapshot):
        if snapshot.metadata.get('camera')!=self.camera:raise InputRejected('Tracking requires the selected paired RGB-D camera')
        if self.snapshot is not None:
            if (snapshot.metadata.get('calibration_id')!=self.snapshot.metadata.get('calibration_id')
                    or snapshot.metadata.get('sensor_serial')!=self.snapshot.metadata.get('sensor_serial')
                    or snapshot.rgb.shape!=self.snapshot.rgb.shape):
                self.points.clear();self.errors.clear()
                raise InputRejected('Tracking calibration/sensor changed; start a new run')
        gray=cv2.cvtColor(snapshot.rgb,cv2.COLOR_RGB2GRAY)
        if self._gray is not None and self.points and snapshot.metadata['captured_at']!=self.snapshot.metadata['captured_at']:
            # Include the boundary of a flat block instead of relying on its
            # untextured center. Keep both flow directions and the 1.5px gate.
            names=list(self.points);before=np.array([self.points[k] for k in names],dtype=np.float32).reshape(-1,1,2)
            after,status,_=cv2.calcOpticalFlowPyrLK(self._gray,gray,before,None,winSize=(41,41),maxLevel=3)
            back,back_status,_=cv2.calcOpticalFlowPyrLK(gray,self._gray,after,None,winSize=(41,41),maxLevel=3) if after is not None else (None,None,None)
            for i,name in enumerate(names):
                valid=(after is not None and back is not None and bool(status[i,0]) and bool(back_status[i,0])
                    and np.isfinite(after[i]).all() and np.linalg.norm(back[i]-before[i])<=1.5)
                if valid:
                    u,v=after[i,0];h,w=gray.shape
                    valid=0<=u<w and 0<=v<h
                if not valid:
                    self.points.pop(name,None);self.errors[name]='Optical flow lost this point; select it again from the current image'
                else:self.points[name]=after[i,0].copy()
        self.snapshot=snapshot;self._gray=gray

    def measure(self, *, camera_poses=None):
        if self.snapshot is None:raise InputRejected('No paired RGB-D frame')
        if not 0<=self.snapshot.age()<=2:raise StaleTrackingDepth('Tracked depth is stale; capture a fresh paired frame')
        if self.camera!='top' and (not isinstance(camera_poses,dict) or set(camera_poses)!={'left','right'}):
            raise InputRejected('Wrist depth requires both current measured arm-base camera poses')
        result={}
        for name,uv in self.points.items():
            try:
                item={}
                for arm in ('left','right'):
                    kwargs={} if self.camera=='top' else {'T_base_camera':camera_poses[arm]}
                    value=self.snapshot.measure(int(round(float(uv[0]))),int(round(float(uv[1]))),arm=arm,**kwargs)
                    if 'point_base_m' not in value:raise InputRejected('No calibrated arm-base transform; camera coordinates are not robot targets')
                    item[arm]=value['point_base_m']
                result[name]=item
                self.errors.pop(name,None)
            except ValueError as exc:self.errors[name]=str(exc)
        return result

    def summary(self):
        return dict(camera=self.camera,captured_at=self.snapshot.metadata['captured_at'] if self.snapshot else None,
                    pixels={k:v.tolist() for k,v in self.points.items()},errors=dict(self.errors))
