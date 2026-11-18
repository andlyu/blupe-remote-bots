"""Prepared host lifecycle over the canonical controller and camera recorder.

Reference: remote_yam.controller.RunnerController.join_and_run and
roboharness_replay.PublicCameraReplay at public source3278346a. This module is
not a readiness grant: the public robot endpoint stays unavailable pending
actual worker/task-scene/physical qualification. Generated code receives no
session, identity, transport or private host path.
"""
import hashlib
import json
import math
from pathlib import Path
import shutil
import threading
import time

from controller_bridge import GeneratedControllerProvider
from simulation_artifacts import LIMITS, read_regular, write_private


def stage_controller(execution_dir, receipt, destination, runner_root, *, image):
    """Stage the exact retained simulation inputs, not the editable job mount."""
    if (receipt.get('binding_passed') is not True or receipt.get('cleanup_confirmed') is not True
            or type(receipt.get('exit_code')) is not int or receipt['exit_code']!=0
            or receipt.get('variant')!='yam1' or receipt.get('image')!=image):
        raise ValueError('A matching completed YAM1 simulation is required for source handoff')
    blobs={name:read_regular(Path(execution_dir)/name,LIMITS[name])
           for name in ('controller.py','station.json')}
    for name,key in (('controller.py','controller_sha256'),('station.json','station_snapshot_sha256')):
        if hashlib.sha256(blobs[name]).hexdigest()!=receipt.get(key):
            raise ValueError('Retained simulation input changed; no controller staged')
    station=json.loads(blobs['station.json'])
    destination=Path(destination);destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    runtime=destination/'controller-runtime';runtime.mkdir(mode=0o700)
    backend=Path(__file__).resolve().parent;runner_root=Path(runner_root)
    for name in ('controller_entry.py','yam1_environment.py','yam1_scene.py','yam1_kinematics.py'):
        write_private(runtime/name,read_regular(backend/name,160000))
    shutil.copytree(backend.parent/'assets',destination/'assets')
    for name in ('models/yam/assets','models/yam_bimanual'):
        shutil.copytree(runner_root/name,destination/'runner'/name)
    safety=destination/'runner/config/controller-workspaces/native-both-20260929.safety.json'
    safety.parent.mkdir(parents=True)
    write_private(safety,read_regular(runner_root/'config/controller-workspaces'/safety.name,64000))
    for name,data in blobs.items():write_private(destination/name,data)
    config=dict(runner_root='/workspace/runner',gripper_dir='/workspace/assets/linear4310',
                skills_root='/opt/robotics/plugins/robotics/skills',calibration=station['calibration'])
    write_private(runtime/'config.json',(json.dumps(config)+'\n').encode())
    return dict(controller_sha256=receipt['controller_sha256'],simulation_execution_id=receipt['id'],
                station_snapshot_sha256=receipt['station_snapshot_sha256'],image=image)


class PhysicalRun:
    """Single-use lifecycle. Controller owns admission and every motor operation.

    Call wait after terminal UI status: the native worker may still be closing
    a provider. Capture has its own finishing thread. Neither terminal status
    nor a completed controller proves a physical object outcome or onset time.
    """
    def __init__(self, runner_root, api, channel, *, controller_sha256,
                 recording_path, replay=None, capture=None):
        from remote_yam.controller import RunnerController
        if replay is None:
            from remote_yam.roboharness_replay import PublicCameraReplay
            replay=PublicCameraReplay(Path(recording_path).parent/'camera-replays',
                                      robot_id='yam-1',model='Gemini Robotics')
        if replay.model!='Gemini Robotics':raise ValueError('Replay must retain Gemini Robotics attribution')
        self.channel=channel;self.replay=replay;self.replay_thread=None
        self.provider=GeneratedControllerProvider(runner_root,channel,
            controller_sha256=controller_sha256,capture=capture,recording_path=recording_path)
        self.controller=RunnerController(api,robot_id='yam-1',recording_root=Path(recording_path).parent)
        self.launch_requested_at=None;self._attempted=False;self._lock=threading.RLock()
        self.cleanup_error=False;self.station_stop_error=False

    def start(self,prompt,run_duration_s,*,launch_requested_at):
        if type(launch_requested_at) not in (int,float) or not math.isfinite(launch_requested_at):
            raise ValueError('Retain the original website Start time')
        with self._lock:
            if self._attempted:raise RuntimeError('A physical run cannot be restarted or replayed')
            if not self.replay.ready():raise RuntimeError('The existing physical replay encoder is unavailable; no queue submitted')
            self._attempted=True;self.launch_requested_at=launch_requested_at
            try:
                self.controller.join_and_run(self.provider,prompt,run_duration_s=run_duration_s)
                self.replay_thread=self.replay.start(self.controller)
            except BaseException:
                # Recorder startup must not orphan an already-started session.
                self.stop('physical_start_failed')
                raise
        return self.status()

    def status(self):
        state=self.controller.status();worker=self.controller._worker
        return dict(status=state['status'],launch_requested_at=self.launch_requested_at,
            native_run_started_at=state.get('run_started_at'),episode_id=state.get('episode_id'),
            queue_position=state.get('queue_position'),packets_submitted=state.get('packets_submitted',0),
            controller_finished=self.provider.completed,outcome_verified=False,
            native_error=bool(state.get('error')),worker_alive=bool(worker and worker.is_alive()),
            capture_alive=bool(self.replay_thread and self.replay_thread.is_alive()),
            cleanup_confirmed=getattr(self.channel,'cleanup_confirmed',False) is True,
            cleanup_error=self.cleanup_error,station_stop_error=self.station_stop_error)

    def stop(self,reason='user_requested'):
        # Revoke station motion first, before waiting for generated execution.
        try:self.controller.stop(reason)
        except BaseException:
            self.station_stop_error=True
            raise
        finally:
            try:self.provider.close()
            except Exception:
                self.cleanup_error=True
                raise
        return self.status()

    def wait(self,timeout_s):
        """Bound the observation wait; never restart an expired/unknown operation."""
        if timeout_s<0 or not math.isfinite(timeout_s):raise ValueError('Invalid wait duration')
        deadline=time.monotonic()+timeout_s;worker=self.controller._worker
        if worker is not None:worker.join(max(0,deadline-time.monotonic()))
        if worker is not None and worker.is_alive():return self.status()
        try:self.provider.close()
        except Exception:
            self.cleanup_error=True
            raise
        if self.replay_thread is not None:self.replay_thread.join(max(0,deadline-time.monotonic()))
        return self.status()
