"""Bounded SSH-loopback I/O through the existing YAM services, never CAN."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import subprocess
import time
import zipfile
import io

from .yam_cube_reset import ResetBlocked, write_new

CUBE_TIMING_PROFILE = 'cube-linear-0.1-0.8-v1'
# Fixed operations and ports. Source-monotonic age is measured on the robot;
# request round trip is added locally instead of subtracting different clocks.
WORKER = r'''
import sys,json,time,base64,urllib.request,urllib.error
routes=globals().get('station_routes',{})
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
 try:
  p=json.loads(line);op=p['op']
  if op in globals().get('extra_operations',{}):
   data=extra_operations[op](p.get('payload'))
   print(json.dumps({'ok':True,'data':data,'robot_received_at':time.time()},separators=(',',':')),flush=True)
   continue
  port,path=routes[op]
  payload=p.get('payload');data=None if payload is None else json.dumps(payload).encode()
  if (op in ('state','pose_status') or op.startswith('capture')) and data is not None:raise ValueError('Read only')
  if op=='hold':data=b'{}'
  req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=data,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=8) as r:
   body=r.read(16000001)
   if len(body)>16000000:raise ValueError('Oversized response')
   result={'ok':True,'robot_received_at':time.time()}
   if op.startswith('capture'):
    result.update(body_b64=base64.b64encode(body).decode(),
      source_age_s=time.monotonic()-float(r.headers['X-Capture-Monotonic']),
      captured_at=float(r.headers['X-Captured-At']),sequence=int(r.headers['X-Frame-Sequence']))
   else:result['data']=json.loads(body)
 except Exception as e:result={'ok':False,'error':str(e)}
 print(json.dumps(result,separators=(',',':')),flush=True)
'''


class FrameBeforeMotion(ResetBlocked):
    pass


class ControllerFault(ResetBlocked):
    pass


def check_controller_fault(state):
    fault = state.get('adapter_fault') or state.get('controller_fault')
    if fault or state.get('mode') == 'FAULT' or state.get('safety', {}).get('controller_ok') is False:
        raise ControllerFault(str(fault or 'Native controller reports FAULT'))


class RobotIO:
    def __init__(self, ssh, identity, evidence, *, accept_late_frames=False,worker_source=None):
        if not ssh or ssh.startswith("-") or any(c.isspace() for c in ssh):
            raise ValueError("An explicit trusted YAM SSH destination is required")
        self.evidence = Path(evidence)
        self.ssh, self.identity = ssh, identity
        self.accept_late_frames = bool(accept_late_frames)
        self.motion_completed_robot_wall = None
        if worker_source is None:
            from .station import resource
            worker_source='station_routes='+repr(resource('io_routes'))+'\n'+WORKER
        self.worker_source=worker_source
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.frame_index = 0
        self._connect()

    def _connect(self):
        command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                   "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes"]
        if self.identity:
            command += ["-i", self.identity]
        command += [self.ssh, "python3 -u -c " + shlex.quote(self.worker_source)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, bufsize=0)
        self.buffer = b""
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.needs_reconnect = False
        try:
            # Measured SSH/Python startup can take 13.5 s on this station.
            # Startup is separate from each frame's unchanged <2 s age gate.
            if not self._line(30).get("ready"):
                raise ResetBlocked("Camera/control SSH worker did not become ready")
        except BaseException:
            self.close()
            raise

    def _line(self, timeout):
        deadline = time.monotonic()+timeout
        while b"\n" not in self.buffer:
            remaining = deadline-time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError("YAM transport timed out; a write is never retried")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise ResetBlocked("YAM SSH connection closed")
            self.buffer += chunk
            if len(self.buffer) > 23_000_000:
                raise ResetBlocked("YAM response exceeds size limit")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def call(self, op, payload=None):
        if getattr(self,'before_request',None) is not None:self.before_request()
        began = time.monotonic()
        self.process.stdin.write(json.dumps(dict(op=op,payload=payload)).encode()+b"\n")
        try:response = self._line(10)
        except (OSError, TimeoutError, ValueError, ResetBlocked):
            self.needs_reconnect = True
            raise
        elapsed = time.monotonic()-began
        receipt = {k:v for k,v in response.items() if k not in ("body_b64", "data")}
        receipt.update(operation=op, local_received_at=time.time(), round_trip_s=elapsed)
        with (self.evidence/"io.jsonl").open("a") as stream:
            stream.write(json.dumps(receipt)+"\n")
        if not response.get("ok"):
            raise ResetBlocked(response.get("error", "Robot request failed"))
        self.last_robot_wall=response["robot_received_at"]
        if op.startswith("capture"):
            return response, elapsed
        return response["data"]

    def continuation_event(self, event, **values):
        with (self.evidence/'continuation.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(event=event, at=time.time(), **values))+'\n')

    def reconnect(self):
        """Replace an uncertain stream; never replay a request or a motor write."""
        self.close()
        self._connect()

    def read(self, operation):
        """Wait for controller status through transport outages without a write."""
        if operation not in ('state', 'pose_status'):
            raise ValueError('Continuation reads are limited to controller status')
        while True:
            try:
                if self.needs_reconnect:self.reconnect()
                result = self.call(operation)
                check_controller_fault(result)
                return result
            except ControllerFault:
                raise
            except (ResetBlocked, OSError, TimeoutError, ValueError) as exc:
                self.continuation_event('controller_read_wait', operation=operation, error=str(exc))
                time.sleep(.2)
                try:self.reconnect()
                except (ResetBlocked, OSError, TimeoutError, ValueError):pass

    def capture(self, report, *, camera="top", after_robot_wall=None):
        # A read-only exposure may be retried. A movement is never retried.
        required = after_robot_wall if after_robot_wall is not None else getattr(self,'motion_completed_robot_wall',None)
        for attempt in range(3):
            try:
                return self._capture_once(report,camera=camera,after_robot_wall=required)
            except FrameBeforeMotion:
                if attempt==2:
                    raise
                time.sleep(.05)

    def _capture_once(self, report, *, camera="top", after_robot_wall=None):
        from remote_yam.api_depth import ApiDepth
        late = getattr(self,'accept_late_frames',False)
        if late:
            from remote_yam.api_depth import depth_robot_stopped
            state = self.call('state')
            if not depth_robot_stopped(state) or not state.get('feedback_available'):
                raise ResetBlocked('Delayed-frame trial requires measured stationary arm feedback')
        if camera not in ("top", "left", "right"):
            raise ValueError("Unknown camera role")
        response, elapsed = self.call("capture" if camera == "top" else "capture_"+camera)
        body = base64.b64decode(response["body_b64"], validate=True)
        path = self.evidence/f"frame-{self.frame_index:04d}.rgbd-native.zip"
        self.frame_index += 1
        path.write_bytes(body)
        age = response["source_age_s"]+elapsed
        receipt = dict(file=path.name, sha256=hashlib.sha256(body).hexdigest(),
                       source_age_s=response["source_age_s"], round_trip_s=elapsed,
                       age_upper_s=age, captured_at=response["captured_at"],
                       sequence=response["sequence"], local_received_at=time.time(),
                       accept_late_frames=late,after_motion_robot_wall=after_robot_wall)
        write_new(path.with_suffix(".receipt.json"),receipt)
        limit = 5. if late else 2.
        if not 0 <= age < limit:
            raise ResetBlocked(f"RGB-D age bound {age:.3f}s exceeds {limit:g}s; image retained as evidence")
        # API decoder receives a same-host monotonic upper bound converted into
        # its injected clock. It is not the Mac minus Jetson wall clock.
        reader = ApiDepth("http://127.0.0.1", camera=camera, clock=lambda:response["captured_at"]+age)
        snapshot = reader.decode(body,report,stopped=late)
        if snapshot.metadata["captured_at"] != response["captured_at"]:
            raise ResetBlocked("Frame header/body timestamps disagree")
        if snapshot.metadata.get("sequence") != response["sequence"]:
            raise ResetBlocked("Frame header/body sequences disagree")
        if after_robot_wall is not None:
            stamps = [snapshot.metadata[k] for k in ("captured_at","color_captured_at","depth_captured_at")
                      if k in snapshot.metadata]
            if min(stamps) <= after_robot_wall:
                raise FrameBeforeMotion("Frame predates completed motion; no later exposure received; no motion retry")
        snapshot.age_upper_s=age
        snapshot.received_monotonic=time.monotonic()
        return snapshot

    def captures(self, report, count=3, *, after_robot_wall=None, camera="top"):
        result=[]
        seen=set()
        for _ in range(count+4):
            s=self.capture(report,after_robot_wall=after_robot_wall,camera=camera)
            key=(s.metadata["captured_at"],s.metadata.get("sequence"))
            if key not in seen:
                result.append(s);seen.add(key)
            if len(result)==count:
                return result
            time.sleep(.2)
        raise ResetBlocked("Not enough distinct fresh RGB-D frames")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.selector.close()
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):stream.close()

    def emergency_hold(self):
        # A timed-out stream may still have a late response buffered. A fresh
        # connection cannot mistake that old response for a Hold acknowledgement.
        with RobotIO(self.ssh,self.identity,self.evidence/"failure-hold") as fresh:
            result=fresh.call("hold")
            if result.get("state")!="held" or result.get("adapter_state")!="STOPPED":
                raise ResetBlocked("Physical Hold was not confirmed")
            return result

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def load_recorded(directory, report):
    """Offline only. Never hand recorded images to a live motion executor."""
    from remote_yam.api_depth import ApiDepth
    paths=sorted(Path(directory).glob("*.rgbd-native.zip"))
    result=[]
    for path in paths:
        body=path.read_bytes()
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            captured=json.loads(archive.read("metadata.json"))["captured_at"]
        # Historical decode at its capture clock, explicitly not fresh evidence.
        snapshot=ApiDepth("http://127.0.0.1",clock=lambda:captured).decode(body,report,stopped=True)
        snapshot.offline=True
        result.append(snapshot)
    return result


def execute_pose(io, joints, grippers, *, timeout=35, owner_token=None, execution_policy='validated',
                 duration_floor_s=None, wait_for_completion=False):
    """Submit once; continuation reconciles late acknowledgements by status."""
    payload=dict(joints_rad=list(joints),grippers=list(grippers),owner_token=owner_token)
    continuing = execution_policy == 'controller-faults'
    if duration_floor_s is not None:
        if type(duration_floor_s) not in (int,float) or duration_floor_s not in (.1,.8):
            raise ResetBlocked('Unqualified cube duration floor')
        payload['duration_floor_s']=duration_floor_s
    while True:
        try:
            preview=io.call("preview",payload)
            break
        except (OSError, TimeoutError, ResetBlocked) as exc:
            if not continuing or (isinstance(exc,ResetBlocked) and not getattr(io,'needs_reconnect',False)):
                raise
            io.continuation_event('preview_wait',error=str(exc))
            # Preview never dispatches motors; only this read/plan may repeat.
            state=io.read('state')
            if state.get('mode') in ('DISABLED','STOPPING'):
                raise KeyboardInterrupt('Operator stopped the controller')
            if io.read('pose_status').get('cancelled'):
                raise KeyboardInterrupt('Operator stopped the local sequence')
    if continuing and preview.get('execution_policy') != execution_policy:
        raise ResetBlocked('Controller did not confirm controller-faults execution; no movement submitted')
    if preview.get("state") != "previewed" or not preview.get("plan_id"):
        raise ResetBlocked("Controller did not validate the complete pose transition")
    if duration_floor_s is not None and (preview.get('duration_floor_s')!=duration_floor_s
            or preview.get('cube_timing_profile')!=CUBE_TIMING_PROFILE):
        raise ResetBlocked('Controller did not confirm the simulation-qualified timing; no execution submitted')
    if wait_for_completion and preview.get('completion_wait_supported') is not True:
        raise ResetBlocked('Controller completion wait unavailable; no execution submitted')
    try:
        try:io.call("execute",dict(plan_id=preview["plan_id"],owner_token=owner_token))
        except (OSError, TimeoutError, ResetBlocked) as exc:
            if not continuing:raise
            io.continuation_event('execute_ack_uncertain', plan_id=preview['plan_id'], error=str(exc))
            # Reconcile by reading this plan's status. Never submit execute twice.
            try:io.reconnect()
            except (OSError, TimeoutError, ResetBlocked):pass
        deadline=time.monotonic()+timeout
        while continuing or time.monotonic()<deadline:
            if wait_for_completion:
                try:
                    state=io.call('wait',dict(plan_id=preview['plan_id'],owner_token=owner_token,
                        timeout_s=5. if continuing else min(2.,max(.001,deadline-time.monotonic()))))
                except ControllerFault:
                    raise
                except (OSError,TimeoutError,ResetBlocked,ValueError) as exc:
                    if not continuing:raise
                    io.continuation_event('completion_wait_uncertain',plan_id=preview['plan_id'],error=str(exc))
                    # A wait is read-only. Reconcile the same plan on a clean
                    # connection; never repeat its execute request.
                    try:io.reconnect()
                    except (OSError,TimeoutError,ResetBlocked,ValueError):pass
                    controller=io.read('state')
                    if controller.get('mode') in ('DISABLED','STOPPING'):
                        raise KeyboardInterrupt('Operator stopped the controller')
                    state=io.read('pose_status')
                check_controller_fault(state)
                if state.get('state')=='interrupted' or state.get('cancelled'):
                    raise KeyboardInterrupt('Local pose was stopped or released')
            elif continuing:
                controller=io.read('state')
                if controller.get('mode') in ('DISABLED','STOPPING'):
                    raise KeyboardInterrupt('Operator stopped the controller')
                state=io.read('pose_status')
                if state.get('state')=='interrupted' or state.get('cancelled'):
                    raise KeyboardInterrupt('Local pose was stopped or released')
            else:state=io.call("pose_status")
            if state.get("plan_id")!=preview["plan_id"]:
                if continuing:
                    io.continuation_event('plan_status_mismatch', expected=preview['plan_id'], observed=state.get('plan_id'))
                    time.sleep(.15)
                    continue
                raise ResetBlocked("Another pose replaced this reset motion")
            if state.get("state")=="holding" and not state.get("active"):
                if getattr(io,'accept_late_frames',False):
                    io.motion_completed_robot_wall=io.last_robot_wall
                return state
            if state.get("state") in ("failed","interrupted"):
                raise ResetBlocked(f"Motion failed: {state}")
            if not wait_for_completion:time.sleep(.15)
        raise TimeoutError("Motion did not complete; no automatic retry")
    except BaseException as exc:
        try:io.emergency_hold()
        except Exception as hold_error:
            raise ResetBlocked(f"Motion result uncertain; Hold also unconfirmed: {hold_error}; original: {exc}") from exc
        raise
