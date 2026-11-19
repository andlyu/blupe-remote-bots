"""Compose source-bound generation with the existing attributed YAM lifecycle.

No public robot route is enabled by importing this module. The worker's current
qualification guard remains in force. Native queue/lease/Home/feedback/Stop own
all physical requests; no timed-out or ambiguous movement is replayed here.
"""
import asyncio
import base64
import os
from pathlib import Path
import time
import uuid

from controller_channel import RootlessControllerChannel
from physical_run import PhysicalRun,stage_controller
from physical_evidence import retain_physical,public_native_event
from quiet_session import GeminiSessionAPI
from station_inputs import API_ORIGIN,runner_root,transport_classes


async def run_physical(store,ident,receipt,*,api_factory=GeminiSessionAPI,
                       channel_factory=RootlessControllerChannel,run_factory=PhysicalRun,
                       stage=stage_controller,poll_s=.1):
    job=store.get(ident)
    if job['mode']!='robot':raise ValueError('Simulation requests cannot enter physical execution')
    run=None;status={};binding=None;stop_sent=False;expired=False;failure=None
    def stopping():return store.get(ident).get('stop_requested_at') is not None
    if stopping():
        store.event(ident,'cancelled','Stopped before robot queue admission')
        return
    image=os.environ.get('GEMINI_SIM_IMAGE','')
    source=store.root/'simulation-evidence'/ident/uuid.UUID(receipt['id']).hex
    workspace=store.root/'physical-jobs'/ident
    directory=store.root/'physical-evidence'/ident/('run_'+uuid.UUID(ident).hex)
    store.event(ident,'preparing_physical','Preparing the simulated controller for the existing robot queue')
    binding=await asyncio.to_thread(stage,source,receipt,workspace,runner_root(),image=image)
    if stopping():
        store.event(ident,'cancelled','Stopped before robot queue admission')
        return
    # Identity is read only here; it is never added to generated inputs/public data.
    email=store.private_email(ident)
    api=api_factory(job['runner_name'],email)
    remaining=max(0,job['created_at']+job['duration_s']-time.time())
    if remaining<=0:raise TimeoutError('Run duration expired before physical queue admission')
    channel=channel_factory(workspace,deadline_monotonic=time.monotonic()+remaining)
    _Api,Cameras=transport_classes();cameras=Cameras(API_ORIGIN)
    def camera_event(kind,message,details):
        store.event(ident,'observing',message)
    def capture(observation):
        frames=cameras.capture_for_policy(observation,cancelled=lambda:run.provider.cancelled(),on_event=camera_event)
        return {frame.name:{**frame.summary(),'jpeg_base64':base64.b64encode(frame.jpeg).decode()} for frame in frames}
    run=run_factory(runner_root(),api,channel,controller_sha256=binding['controller_sha256'],
                    recording_path=directory,capture=capture)
    last=None;seen_events=set()
    async def stop_once(reason):
        nonlocal stop_sent,failure
        if stop_sent:return
        stop_sent=True
        store.event(ident,'stopping','Requesting Stop from the controller; waiting for acknowledgement and recording')
        try:await asyncio.to_thread(run.stop,reason)
        except Exception:failure='Stop acknowledgement or controller cleanup is unverified'
    try:
        await asyncio.to_thread(run.start,job['prompt'],job['duration_s'],
                                launch_requested_at=job.get('launch_requested_at') or job['created_at'])
        while True:
            status=await asyncio.to_thread(run.wait,.05)
            if stopping():await stop_once('user_requested')
            elif status['worker_alive'] and time.time()>=job['created_at']+job['duration_s']:
                expired=True;await stop_once('policy_runtime_timeout')
            if stop_sent:status=run.status()
            projection={**status,'outcome_verified':False}
            store.physical_status(ident,projection)
            generation,events=run.native_events();latest_note=None
            for row in events:
                key=(generation,row['id'])
                if key in seen_events:continue
                seen_events.add(key)
                note=public_native_event(row)
                if note:
                    store.note(ident,**note);latest_note=note
            if latest_note and status['worker_alive'] and not stop_sent:
                store.update(ident,state=latest_note['stage'],progress=latest_note['message'])
            current=(status['status'],status['queue_position'],status['worker_alive'],status['capture_alive'])
            if current!=last and not stop_sent and not (latest_note and status['worker_alive']):
                if status['worker_alive']:
                    phase,message={
                        'queued':('robot_queue','Waiting for the existing YAM1 queue to grant this run'),
                        'preparing':('preparing_physical','Controller is preparing the isolated runtime and robot'),
                        'running':('running','Executing the generated controller on YAM1; recording actual cameras'),
                    }.get(status['status'],('preparing_physical','Waiting for the canonical controller lifecycle'))
                else:phase,message='finalizing','Controller finished; finalizing retained physical footage'
                store.event(ident,phase,message);last=current
            if not status['worker_alive'] and not status['capture_alive']:break
            await asyncio.sleep(poll_s)
    except asyncio.CancelledError:
        await asyncio.shield(stop_once('worker_cancelled'))
        # Observe the same worker/capture rather than starting another operation.
        status=await asyncio.shield(asyncio.to_thread(run.wait,15))
        failure='Worker execution was interrupted; physical outcome requires review'
        raise
    except Exception:
        failure='Physical controller or recording failed; no movement was replayed'
        await stop_once('physical_execution_failed')
        try:status=await asyncio.to_thread(run.wait,15)
        except Exception:status=run.status()
    finally:
        if run is not None:
            if not status:status=run.status()
            store.physical_status(ident,status)
            result,artifacts=await asyncio.to_thread(retain_physical,store.root,job,binding,status,run.replay.root)
            store.retain_physical(ident,artifacts)
            if (status.get('worker_alive') or status.get('capture_alive') or not status.get('cleanup_confirmed')
                    or status.get('cleanup_error') or status.get('station_stop_error')):
                failure='Controller Stop, worker exit or recording cleanup remains unverified'
            if failure:store.event(ident,'failed',failure)
            elif stopping():store.event(ident,'cancelled','Stop acknowledged; physical recording finalized' if result['capture_status']=='ready' else 'Stop acknowledged; physical footage unavailable, receipt retained')
            elif status.get('native_error'):store.event(ident,'failed','Canonical controller reported an error; review run details and robot connection before retrying')
            elif result['capture_status']!='ready':store.event(ident,'failed','Physical footage is unavailable; retained receipt explains the gap')
            elif expired:store.event(ident,'failed','Run duration expired; recording and controller receipt retained')
            elif status.get('controller_finished') and not status.get('native_error'):
                store.event(ident,'complete','Controller execution and recording finished; physical outcome requires review')
            else:store.event(ident,'failed','Canonical execution ended without verified controller completion; review retained footage')
