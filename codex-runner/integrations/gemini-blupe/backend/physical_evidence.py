"""Retain host camera footage/receipts outside the generated controller mount.

Native PublicCameraReplay provides source/receive/presentation UTC; these fields
never establish object success, Home completion or observed method onset alone.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import time

from simulation_artifacts import read_regular,write_private

STATUS_FIELDS=('status','launch_requested_at','native_run_started_at','episode_id',
    'queue_position','packets_submitted','controller_finished','outcome_verified',
    'native_error','worker_alive','capture_alive','cleanup_confirmed','cleanup_error','station_stop_error')


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def public_status(status):
    result={}
    for key in STATUS_FIELDS:
        value=status.get(key)
        if key=='status':
            result[key]=value if isinstance(value,str) and value in {'idle','queued','preparing','running','resetting','stopped','complete','completed','failed','cancelled','timed_out','safety_aborted','disconnected'} else 'unknown'
        elif key=='episode_id':
            result[key]=value if isinstance(value,str) and re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',value) else None
        elif key in {'launch_requested_at','native_run_started_at','queue_position','packets_submitted'}:
            result[key]=value if finite(value) else None
        else:result[key]=value if type(value) is bool else None
    result['outcome_verified']=False
    return result


def public_native_event(row):
    """Expose command boundaries without native config/capabilities/paths."""
    kind=row.get('kind');stamp=row.get('timestamp')
    if not isinstance(kind,str) or not finite(stamp):return None
    labels={
        'controller_preparing':('preparing_physical','Starting the isolated controller before queue admission'),
        'controller_ready':('preparing_physical','Controller runtime ready; requesting normal robot admission'),
        'joined':('robot_queue','Robot queue request acknowledged; waiting for lease and readiness'),
        'controller_compiled':('running','Method packet passed local validation; no dispatch implied'),
        'packet_submit':('dispatching','Sending the validated packet; waiting for gateway acceptance'),
        'packet_dispatched':('dispatching','Packet accepted for dispatch; waiting for gateway validation'),
        'packet_accepted':('executing','Gateway validated the packet; waiting for measured completion'),
        'packet_completed':('running','Measured feedback completed this method packet'),
        'packet_error':('execution_error','Gateway reported a packet error; no movement is replayed'),
        'controller_execution_failed':('execution_error','Canonical execution failed; no automatic movement retry'),
        'replay_capture':('running','Recording actual camera footage while the controller runs'),
        'replay_encoding':('finalizing','Capture finished; finalizing retained physical playback'),
        'replay_failed':('recording_error','Recording preparation failed; captured frames remain for recovery'),
        'stop_requested':('stopping','Canonical Stop requested; waiting for acknowledgement'),
        'stopped':('stopping','Canonical Stop acknowledged; finalizing worker and capture'),
    }
    if kind=='controller_rejected':
        # Validation feedback goes privately to the generated controller. Native
        # messages may embed arbitrary field names/values, so publish no raw text.
        stage,message='running','Local command rejected before dispatch; waiting for corrected controller input'
    elif kind=='lifecycle':
        reason=(row.get('details') or {}).get('reason')
        if reason=='jetson_leased':stage,message='preparing_physical','Robot lease granted; native preparation is in progress'
        else:return None
    elif kind in labels:stage,message=labels[kind]
    else:return None
    return dict(stage=stage,message=message,at=stamp)


def retain_physical(root,job,binding,status,replay_root):
    """Project only public fields; never publish native journals/private headers."""
    root=Path(root);ident=job['id'];folder=root/'physical-evidence'/ident
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    result=dict(schema_version=1,run_id=ident,robot_id='yam-1',model='Gemini Robotics',
        mode='physical',created_at=time.time(),image=binding.get('image'),
        source_revision=job['configuration'].get('source_revision'),controller_sha256=binding['controller_sha256'],
        simulation_execution_id=binding['simulation_execution_id'],
        status=public_status(status),capture_status='unavailable',
        outcome_verified=False,timing=dict(t_run=job.get('launch_requested_at'),
            start_clock_source=job['configuration'].get('start_clock_source','server_received_legacy'),
            server_received_at=job['created_at'],t_queue=None,t_admit=None,t_home=None,t_motion=None,
            excluded_queue_s=None,run_target='unverified',home_target='unverified'))
    blobs={};episode=status.get('episode_id')
    try:
        if not isinstance(episode,str) or re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}',episode) is None:
            raise ValueError('No matched episode')
        replay_root=Path(replay_root)
        meta=json.loads(read_regular(replay_root/(episode+'.json'),1024*1024))
        info=meta['preview'];digest=info['sha256']
        if (meta.get('episode_id')!=episode or meta.get('robot_id')!='yam-1'
                or meta.get('model')!='Gemini Robotics' or info.get('camera_order')!=['top']
                or type(digest) is not str or re.fullmatch(r'[a-f0-9]{64}',digest) is None
                or not finite(info.get('duration_s')) or info['duration_s']<=0
                or not finite(info.get('speed')) or info['speed']!=1 or meta.get('capture_source')!='public_top_camera'):
            raise ValueError('Capture identity or presentation differs')
        if any(meta.get(key) is not None and not finite(meta[key]) for key in ('started_at','ended_at')):
            raise ValueError('Invalid capture clock')
        frames=meta['frames']
        if not isinstance(frames,list) or not 1<=len(frames)<=1220:raise ValueError('Invalid camera timeline')
        timeline=[]
        for frame in frames:
            row={key:frame.get(key) for key in ('video_at','received_at','source_captured_at','actual_image','presentation_hold')}
            if (not finite(row['video_at']) or not finite(row['received_at'])
                    or type(row['actual_image']) is not bool
                    or row['presentation_hold'] is not None and type(row['presentation_hold']) is not bool
                    or row['source_captured_at'] is not None and not finite(row['source_captured_at'])
                    or (row['actual_image'] and not finite(row['source_captured_at']))):
                raise ValueError('Invalid source camera timing')
            timeline.append(row)
        if not any(frame['actual_image'] for frame in timeline):raise ValueError('No source frames')
        data=read_regular(replay_root/episode/(digest+'.mp4'),16*1024*1024)
        if len(data)!=meta['bytes'] or hashlib.sha256(data).hexdigest()!=digest or b'ftyp' not in data[:32]:
            raise ValueError('Capture checksum or file differs')
        existing=folder/'physical.mp4'
        if existing.exists() and hashlib.sha256(read_regular(existing,16*1024*1024)).hexdigest()!=digest:
            raise ValueError('Previously retained physical footage cannot be replaced')
        blobs['physical.mp4']=data
        result.update(capture_status='ready',capture_source='public_top_camera',
            capture_partial=meta.get('capture_partial') is True,frames=timeline,
            preview=dict(sha256=digest,duration_s=info['duration_s'],speed=1,camera_order=['top']),
            capture_started_at=meta.get('started_at'),capture_ended_at=meta.get('ended_at'))
    except (OSError,ValueError,KeyError,TypeError):
        result['capture_issue']='Matched physical recording is missing or failed verification'
    blobs['physical.json']=(json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    artifacts=[]
    for name,data in blobs.items():
        write_private(folder/name,data)
        artifacts.append(dict(name=name,kind='physical',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                              url=f'/api/runs/{ident}/artifacts/{name}'))
    return result,artifacts
