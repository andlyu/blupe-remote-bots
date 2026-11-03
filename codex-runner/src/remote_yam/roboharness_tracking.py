"""Persistent image points, bidirectional optical flow and calibrated depth.

Tracking uses only the overhead camera. Coordinates returned for actuation are
fresh shared RGB-D measurements in the explicitly calibrated arm-base frames.
Lost/occluded points never become guessed robot targets.
"""
import re
import cv2
import numpy as np

from .roboharness_control import InputRejected, number


class KeypointTracker:
    def __init__(self):
        self.snapshot=None;self.points={};self.errors={};self._gray=None

    def register(self, point_id, u, v):
        if self.snapshot is None:raise InputRejected('Capture paired RGB-D before selecting a point')
        if not isinstance(point_id,str) or not re.fullmatch(r'point_(?:[0-9]|1[0-5])',point_id):
            raise InputRejected('Point ID must be point_0 through point_15')
        u=number(u,'normalized u',0,1000);v=number(v,'normalized v',0,1000)
        h,w=self.snapshot.rgb.shape[:2]
        # 1000 names the last pixel, rather than an out-of-bounds image edge.
        self.points[point_id]=np.array([u*(w-1)/1000,v*(h-1)/1000],dtype=np.float32)
        self.errors.pop(point_id,None)

    def update(self,snapshot):
        if snapshot.metadata.get('camera')!='top':raise InputRejected('RoboHarness tracking requires the overhead RGB-D camera')
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

    def measure(self):
        if self.snapshot is None:raise InputRejected('No paired RGB-D frame')
        if not 0<=self.snapshot.age()<=2:raise InputRejected('Tracked depth is stale; capture a fresh paired frame')
        result={}
        for name,uv in self.points.items():
            try:
                item={}
                for arm in ('left','right'):
                    value=self.snapshot.measure(int(round(float(uv[0]))),int(round(float(uv[1]))),arm=arm)
                    if 'point_base_m' not in value:raise InputRejected('No calibrated arm-base transform; camera coordinates are not robot targets')
                    item[arm]=value['point_base_m']
                result[name]=item
                self.errors.pop(name,None)
            except ValueError as exc:self.errors[name]=str(exc)
        return result

    def summary(self):
        return dict(camera='top',captured_at=self.snapshot.metadata['captured_at'] if self.snapshot else None,
                    pixels={k:v.tolist() for k,v in self.points.items()},errors=dict(self.errors))
