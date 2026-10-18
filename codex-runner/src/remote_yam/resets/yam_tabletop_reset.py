"""One-shot primary box replay followed by the existing tabletop cube reset.

The replay service and cube runner retain motor ownership and Stop handling.
This module schedules them sequentially; it never constructs a motor driver.
"""
from __future__ import annotations
from .station import resource

import json
import os
import time
from pathlib import Path

from .yam_cube_reset import ResetBlocked


def sequence_worker(runtime_root=None):
    """Use one configured SSH worker for Replay, observations and cube poses."""
    from .yam_cube_reset_io import WORKER
    from . import replay_transport
    source=Path(replay_transport.__file__).read_text()
    config=resource('replay')
    prefix='import json\n_replay_namespace={"__name__":"reset_replay_transport"}\n'
    prefix+='exec(compile('+repr(source)+',"reset_replay_transport","exec"),_replay_namespace)\n'
    prefix+='_replay_client=_replay_namespace["ReplayTransport"]('+repr(config)+')\n'
    prefix+='station_routes='+repr(resource('io_routes'))+'\n'
    prefix+='extra_operations={name:(lambda payload,operation=name:_replay_client.operation(operation,payload)) for name in ("replay_start","replay_status","replay_hold")}\n'
    return prefix+WORKER


def cube_arguments(runtime,output,ssh,identity,request_id):
    """Station inputs passed to the public in-process pick/place entry point."""
    argv=list(resource('cube_args'))
    return argv+['--output',str(output),'--ssh',ssh,'--identity',identity or '',
                 '--after-replay',request_id,'--accept-late-frames']


def require_replay_complete(replay, request_id):
    if (replay.get('request_id') != request_id or replay.get('phase') != 'complete'
            or replay.get('running') is not False or replay.get('error')
            or replay.get('controller_fault') or replay.get('finish_action') != 'held'
            or not replay.get('total') or replay.get('completed') != replay.get('total')
            or replay.get('motor_owner') != 'primary_controller'):
        raise ResetBlocked('Matching primary replay did not finish in Hold; cube reset will not start')


def require_replay_handoff(state, pose, request_id):
    """Read-only continuity check: a Stop must not become an automatic Launch."""
    require_replay_complete(state.get('replay', {}), request_id)
    if (state.get('mode') not in ('STOPPED', 'READY') or state.get('launched') is not True
            or state.get('feedback_available') is not True or state.get('adapter_fault')
            or state.get('safety', {}).get('controller_ok') is not True
            or state.get('safety', {}).get('drives_enabled') is not True
            or pose.get('active') is not False or pose.get('sequence_reserved') is not False
            or pose.get('cancelled') is True
            or state.get('auto_queue', {}).get('enabled') is not False
            or state.get('auto_queue', {}).get('running') is not False
            or state.get('api', {}).get('authorized') is not False
            or state.get('api', {}).get('session_id', 'unknown') is not None):
        raise ResetBlocked('Replay handoff is stopped, disabled or owned; cube reset will not initialize or move')


def require_initial_idle(state, pose):
    # Initial disabled startup is supported by the existing replay harness.
    # No extra Home/Zero is issued by this orchestrator.
    if (state.get('mode') not in ('DISABLED', 'STOPPED', 'READY') or state.get('adapter_fault')
            or state.get('replay', {}).get('running') is not False
            or pose.get('active') is not False or pose.get('sequence_reserved') is not False
            or state.get('auto_queue', {}).get('enabled') is not False
            or state.get('auto_queue', {}).get('running') is not False
            or state.get('api', {}).get('authorized') is not False
            or state.get('api', {}).get('session_id', 'unknown') is not None):
        raise ResetBlocked('Primary controller is busy, faulted or has another owner; no replay requested')


def validate_recipe(recipe):
    expected=resource('replay_recipe')
    if (recipe!=expected or recipe.get('schema')!='abc-replay-edit-v1'
            or recipe.get('return_home') is not False or not recipe.get('source_sha256')
            or not recipe.get('calibration_id')):
        raise ResetBlocked('Combined recipe differs from the selected immutable box replay')
    return recipe


def timing_summary(cube_output):
    """Measured, non-overlapping command durations plus labeled process overhead."""
    root = Path(cube_output)
    events_path = root/'events.json'
    events = json.loads(events_path.read_text()) if events_path.exists() else []
    motions = [json.loads(p.read_text()) for p in root.rglob('motion-*.json')]
    sensor_wall = sum(r.get('wall_s', 0.) for r in events if r.get('event') == 'scene_timing')
    wrist_wall = sum(r.get('wall_s', 0.) for r in events if r.get('event') == 'wrist_timing')
    planning_wall = sum(r.get('wall_s', 0.) for r in events if r.get('event') == 'planning_timing')
    # Initial capture runs before feedback orchestration; its transport receipt
    # durations are recorded independently and not added to feedback scene time.
    io_path = root/'transport/io.jsonl'
    if not io_path.exists():io_path=root.parent/'transport/io.jsonl'
    io_rows = [json.loads(line) for line in io_path.read_text().splitlines()] if io_path.exists() else []
    initial_captures = json.loads((root/'initial-captures.json').read_text()) if (root/'initial-captures.json').exists() else []
    initial_sequences = {r['sequence'] for r in initial_captures if 'sequence' in r}
    initial_camera_io = sum(r.get('round_trip_s', 0.) for r in io_rows
                            if r.get('operation') == 'capture' and r.get('sequence') in initial_sequences)
    home=[r for r in motions if r.get('pending',{}).get('color')=='startup' and r.get('pending',{}).get('stage')=='home']
    return dict(cube_motion_command_wall_s=sum(r.get('command_wall_s', 0.) for r in motions if r not in home),
                home_command_wall_s=sum(r.get('command_wall_s',0.) for r in home),home_commands=len(home),
                motion_commands=len(motions),cube_motion_commands=len(motions)-len(home), overhead_scene_wall_s=sensor_wall,wrist_observation_wall_s=wrist_wall,
                pickup_planning_wall_s=planning_wall, initial_camera_io_s=initial_camera_io,
                initial_capture_scope='Camera transport only; initial fit/process startup remain in unallocated cube wall',
                motion_scope='Native preview/execute/completion wait; excludes wrist observations and planning',
                startup_movements=[r for r in events if r.get('event') in ('native_startup', 'startup_planning_home')])


class TabletopResetSequence:
    def __init__(self, args, *, io, cube_program):
        self.args, self.io, self.cube_program = args, io, cube_program
        self.snapshot=lambda:(io.call('state'),io.call('pose_status'))
        self.out = Path(args.output)
        self.request_id = args.request_id
        self.timings = {}
        self.timeline = []

    def save(self, name, value):
        path=self.out/name
        temporary=path.with_suffix(path.suffix+'.writing')
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
        os.replace(temporary,path)

    def status(self, state, **details):
        row=dict(state=state,phase=state,request_id=self.request_id,updated_at=time.time(),**details)
        self.timeline.append(row)
        self.save('timeline.json',self.timeline)
        self.save('status.json',row)

    def run(self):
        started = time.monotonic()
        self.status('preflight')
        recipe = validate_recipe(json.loads(self.args.recipe.read_text()))
        self.save('replay-recipe.json', recipe)
        self.save('sequence-request.json', dict(request_id=self.request_id, recipe=recipe,
                  direction='recorded box emptying -> saved tabletop goals', movement_retry=False,
                  interstage_motion='One user-selected native Home before fresh cube sensing' if '--home-after-replay' in resource('cube_args') else 'None; continue from measured joints',
                  cube_command=str(self.args.cube_command)))
        state, pose = self.snapshot()
        self.save('before.json', dict(controller=state, local_pose=pose))
        require_initial_idle(state, pose)
        self.status('replay')
        replay_started = time.monotonic()
        replay=self.io.call('replay_start',dict(episode=recipe['episode'],edit_recipe=recipe,request_id=self.request_id))
        while replay.get('running') is True:
            if replay.get('request_id')!=self.request_id:
                raise ResetBlocked('Another Replay replaced this sequence; reset not launched')
            if time.monotonic()-replay_started>self.args.replay_timeout:
                raise TimeoutError('Replay completion uncertain; no movement retry or cube launch')
            self.save('replay-progress.json',replay)
            time.sleep(.1)
            replay=self.io.call('replay_status')
        self.timings['replay_command_wall_s'] = time.monotonic()-replay_started
        self.save('replay-result.json', replay)
        require_replay_complete(replay, self.request_id)
        self.io.motion_completed_robot_wall=self.io.last_robot_wall
        handoff_started = time.monotonic()
        self.status('handoff')
        # Engine phase can become complete just before primary finish releases
        # its physical lock. Wait only for that read-only ownership transition.
        while True:
            state, pose = self.snapshot()
            if state.get('mode') != 'REPLAYING':
                break
            if time.monotonic()-handoff_started > 5:
                raise ResetBlocked('Primary replay did not release ownership; reset not launched')
            time.sleep(.05)
        self.save('handoff.json', dict(controller=state, local_pose=pose))
        require_replay_handoff(state, pose, self.request_id)
        self.timings['interstage_handoff_wall_s'] = time.monotonic()-handoff_started
        cube_started = time.monotonic()
        self.status('reset')
        code=self.cube_program(cube_arguments(self.args.cube_command.parent,self.out/'cube-reset',
                               self.args.ssh,self.args.identity,self.request_id),shared_io=self.io)
        self.timings['cube_program_wall_s'] = time.monotonic()-cube_started
        cube = json.loads((self.out/'cube-reset/result.json').read_text())
        state, pose = self.snapshot()
        self.save('terminal.json', dict(controller=state, local_pose=pose))
        self.timings.update(timing_summary(self.out/'cube-reset'))
        self.timings['cube_other_wall_s'] = self.timings['cube_program_wall_s']-sum(
            self.timings[key] for key in ('cube_motion_command_wall_s','home_command_wall_s','overhead_scene_wall_s',
                                         'wrist_observation_wall_s','pickup_planning_wall_s'))
        self.timings['total_wall_s'] = time.monotonic()-started
        result = dict(state=cube['state'], goals_reached=cube.get('goals_reached', False),
                      comparison=cube.get('comparison'), timings=self.timings,
                      terminal_mode=state.get('mode'), torque_off_verified=state.get('safety', {}).get('torque_off_verified'),
                      request_id=self.request_id, physical_trial_count=1,
                      qualification='One combined trial only; camera metric error, no independent physical metrology')
        self.save('result.json', result)
        self.status(result['state'],goals_reached=result['goals_reached'])
        if code not in (0,2):raise KeyboardInterrupt('Cube program cancelled; existing Hold receipt retained')
        return result
