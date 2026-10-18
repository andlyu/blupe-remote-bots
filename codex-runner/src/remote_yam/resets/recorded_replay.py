"""Replay saved bimanual commands through the existing guarded motor owner."""
import json
import math
import threading
import time
from pathlib import Path
import numpy as np

JOINTS = [0,1,2,3,4,5,7,8,9,10,11,12]
GRIPS = [6,13]
HZ = 30
GRIP_LIMIT = .15


def plan(payload):
    actions = np.asarray(payload['actions'], dtype=float)
    times = np.asarray(payload['times'], dtype=float)
    if actions.ndim != 2 or actions.shape[1] != 14 or not 2 <= len(actions) <= 9000:
        raise ValueError('Expected 2–9000 bimanual command rows')
    if times.shape != (len(actions),) or not np.isfinite(actions).all() or not np.isfinite(times).all():
        raise ValueError('Invalid command data')
    if np.any(np.diff(times)<=0) or times[-1]-times[0]>300:
        raise ValueError('Invalid recording timing')
    if np.any(actions[:,GRIPS]<0) or np.any(actions[:,GRIPS]>1):
        raise ValueError('Gripper values must be normalized 0–1')
    rows=[actions[0]]
    for index,(start,end) in enumerate(zip(actions[:-1],actions[1:])):
        count=max(1,math.ceil((times[index+1]-times[index])*HZ),
                  math.ceil(float(np.max(np.abs(end[JOINTS]-start[JOINTS])))/(.30/HZ)),
                  math.ceil(float(np.max(np.abs(end[GRIPS]-start[GRIPS])))/.02))
        if len(rows)+count > 18000:raise ValueError('Replay exceeds ten-minute motion limit')
        rows.extend(start+(end-start)*i/count for i in range(1,count+1))
    return np.asarray(rows)


class RecordedReplay:
    def __init__(self, bridge, *, episode_root=None, settle_tolerance_rad=.04, park_after=True, guard=None, wait_for_settle=True):
        self.bridge=bridge
        self.episode_root=None if episode_root is None else Path(episode_root)
        self.guard=guard
        if not isinstance(park_after,bool):raise ValueError('park_after must be boolean')
        self.park_after=park_after
        self.settle_tolerance_rad=settle_tolerance_rad
        if not isinstance(wait_for_settle,bool):raise ValueError('wait_for_settle must be boolean')
        self.wait_for_settle=wait_for_settle
        self.lock=threading.RLock()
        self.thread=None
        self.cancel=threading.Event()
        self.state={'phase':'idle','running':False,'completed':0,'total':0,'error':None}

    def status(self):
        with self.lock:return dict(self.state,park_after=self.park_after,wait_for_settle=self.wait_for_settle,home_available=True,
                                  guard_mode=getattr(self.guard,'mode','strict_geometry'))

    def start(self, episode):
        import re
        if not isinstance(episode,str) or not re.fullmatch(r'physical-[0-9]+',episode):
            raise ValueError('Invalid episode ID')
        if self.episode_root is None:raise ValueError('Configure the recording directory before replay')
        payload=json.loads((self.episode_root/f'{episode}.json').read_text())
        if payload.get('episode')!=episode:raise ValueError('Replay episode identity mismatch')
        # Validate data before reserving the controller. Geometry is checked in worker.
        actions=plan(payload)
        return self._begin(actions,episode=episode,kind='replay')

    def home(self):
        """Explicit manual Home through this motor owner; never a saved episode."""
        b=self.bridge
        with b.lock:
            if b.error:
                b.clear_fault()  # Existing idle/native-health gate; never clears a motor fault.
            return self._begin(None,kind='home')

    def _begin(self,actions,*,episode=None,kind):
        b=self.bridge
        with b.lock, self.lock:
            if self.state['running'] or b.connected or b.park_ticket is not None or b.controller.active:
                raise RuntimeError('Stop recording or parking before replay')
            if b.error or b.controller.adapter.fault:raise RuntimeError('Resolve controller fault before replay')
            if b.thread and b.thread.is_alive():raise RuntimeError('Teleop is still stopping')
            self.cancel=threading.Event()
            b.connected=True  # Reserve ownership against other recording clients.
            count=len(actions) if actions is not None else 0
            self.state=dict(phase='preflight',running=True,episode=episode,kind=kind,completed=0,total=count,error=None,
                            seconds=count/HZ,gripper_limit=GRIP_LIMIT)
            self.thread=threading.Thread(target=self._run,args=(actions,),daemon=True,name='recorded-replay')
            self.thread.start()
            return self.status()

    def stop(self):
        self.cancel.set()
        self.bridge.controller.cancel.set()
        self.bridge.controller.adapter.hold()
        return {'stopping':True}

    def _run(self, actions):
        is_home=actions is None
        b=self.bridge;c=b.controller;adapter=c.adapter
        guard=self.guard if self.guard is not None else c.operator._safety_guardrails
        cfg=c.operator._safety_config
        timer=threading.Timer(720,self.cancel.set);timer.daemon=True;timer.start()
        def update(**values):
            with self.lock:self.state.update(values)
        def checked(start, points, hz):
            for offset in range(0,len(points),cfg.max_waypoints):
                if self.cancel.is_set():raise RuntimeError('Replay stopped')
                part=points[offset:offset+cfg.max_waypoints]
                guard.approve(start,part,cadence_hz=hz)
                start=part[-1]
        def validate(index,measured,target):
            from remote_yam.resets.tracking import check_tracking_sweep
            check_tracking_sweep(guard,cfg,measured,target)
            return tuple(target)
        def execute(points,grips,hz):
            if self.cancel.is_set():raise RuntimeError('Replay stopped')
            # Reject batch-entry gripper mismatch BEFORE adapter.execute(), whose
            # generic exception path disables motors. Retain hold on this rejection.
            snap,stamp=adapter.snapshot_with_timestamp()
            if not 0<=time.monotonic()-stamp<.1:raise RuntimeError('Follower feedback is stale')
            measured=np.array([snap.left.gripper,snap.right.gripper])
            delta=np.abs(np.asarray(grips[0])-measured)
            if np.max(delta)>GRIP_LIMIT:
                arm=('left','right')[int(np.argmax(delta))]
                raise RuntimeError(f'{arm} gripper entry delta {float(np.max(delta)):.4f} exceeds {GRIP_LIMIT:.2f}; holding')
            adapter.execute(tuple(map(tuple,points)),cadence_hz=hz,gripper_waypoints=tuple(map(tuple,grips)),
                max_gripper_delta_per_step=GRIP_LIMIT,validate_waypoint=validate,cancel_event=self.cancel,
                settle_tolerance_rad=self.settle_tolerance_rad,settle_timeout_s=5,disable_on_settle_timeout=False,
                **({'wait_for_settle':False} if not self.wait_for_settle else {}))
        try:
            if is_home:
                c.prepare()
                if not c.operator.launched:raise RuntimeError(c.state)
                snap,stamp=adapter.snapshot_with_timestamp()
                if not 0<=time.monotonic()-stamp<.1:raise RuntimeError('Follower feedback is stale')
                target=np.asarray(c.operator.park_pose,dtype=float)
                if target.shape!=(12,) or not np.isfinite(target).all():raise ValueError('Invalid configured Home pose')
                # Calibrated zero may be exactly on a hard bound. Keep arithmetic
                # one microradian inside; do not change limits or calibration.
                target=np.clip(target,np.asarray(cfg.joint_lower_rad)+1e-6,np.asarray(cfg.joint_upper_rad)-1e-6)
                actions=np.zeros((2,14));actions[:,JOINTS]=target
                actions[:,GRIPS]=(snap.left.gripper,snap.right.gripper)
                update(target_joints_rad=target.tolist())
            joints=actions[:,JOINTS]
            checked(joints[0],joints,HZ)
            if self.cancel.is_set():raise RuntimeError('Replay stopped')
            update(phase='prepositioning')
            c.prepare()
            if not c.operator.launched:raise RuntimeError(c.state)
            with c.lock:c.active=True
            snap,stamp=adapter.snapshot_with_timestamp()
            if not 0<=time.monotonic()-stamp<.1:raise RuntimeError('Follower feedback is stale')
            q=np.array((*snap.left.joints_rad,*snap.right.joints_rad))
            grips=np.array([snap.left.gripper,snap.right.gripper])
            legal=np.clip(q,cfg.joint_lower_rad,cfg.joint_upper_rad)
            ticks=max(30,math.ceil(1.875*float(np.max(np.abs(joints[0]-legal)))/.20*10),
                      math.ceil(float(np.max(np.abs(actions[0,GRIPS]-grips)))/.02))
            u=np.arange(1,ticks+1)/ticks;blend=10*u**3-15*u**4+6*u**5
            approach=legal+blend[:,None]*(joints[0]-legal)
            grip_path=grips+u[:,None]*(actions[0,GRIPS]-grips)
            if not np.array_equal(q,legal):
                approach=np.vstack((legal,approach));grip_path=np.vstack((grips,grip_path))
            checked(q,approach,10)
            if is_home:update(phase='homing',total=len(approach),seconds=len(approach)/10)
            for offset in range(0,len(approach),cfg.max_waypoints):
                execute(approach[offset:offset+cfg.max_waypoints],grip_path[offset:offset+cfg.max_waypoints],10)
                if is_home:update(completed=min(len(approach),offset+cfg.max_waypoints))
            if not is_home:
                update(phase='replaying')
                for offset in range(0,len(joints),cfg.max_waypoints):
                    end=min(len(joints),offset+cfg.max_waypoints)
                    execute(joints[offset:end],actions[offset:end,GRIPS],HZ)
                    update(completed=end)
            if self.cancel.is_set():raise RuntimeError('Replay stopped')
            snap,stamp=adapter.snapshot_with_timestamp()
            if not 0<=time.monotonic()-stamp<.1:raise RuntimeError('Follower feedback is stale')
            measured=np.array((*snap.left.joints_rad,*snap.right.joints_rad))
            residual_deg=np.degrees(np.abs(measured-joints[-1]))
            update(final_joint_error_deg=residual_deg.tolist(),max_final_joint_error_deg=float(np.max(residual_deg)),
                   accuracy_is_completion_gate=self.wait_for_settle)
            with c.lock:c.active=False
            do_park=self.park_after and not is_home
            if do_park:
                update(phase='parking')
                c.park(cancel_event=self.cancel)
            else:
                adapter.hold()
            update(phase='complete',finish_action='parked' if do_park else 'held',
                   torque_off_verified=adapter.torque_off_verified)
        except Exception as exc:
            try:adapter.hold()
            except Exception:pass
            if not self.cancel.is_set():b.error=str(exc)
            update(phase='stopped' if self.cancel.is_set() else 'failed',error=str(exc),
                   torque_off_verified=adapter.torque_off_verified)
        finally:
            timer.cancel()
            with c.lock:c.active=False
            with b.lock:
                b.connected=False
                update(running=False)
