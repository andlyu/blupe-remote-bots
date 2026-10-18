"""Importable replay→measured cube-reset implementation with injected resources."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
from types import SimpleNamespace
import uuid

from .station import configured
from .yam_cube_reset_io import RobotIO
from .yam_tabletop_reset import TabletopResetSequence,sequence_worker


def run_reset(config,output,*,request_id=None,cancelled=lambda:False,io_factory=RobotIO,cube_program=None):
    """Run once through the existing controller; return and save its outcome.

    config supplies resources, transport, immutable replay recipe and cube inputs.
    A caller may inject an established I/O connection factory and cube executor
    for integration tests. No private repository is imported or searched.
    """
    from .cube_cli import main as cube_main
    config=json.loads(Path(config).read_text()) if isinstance(config,(str,Path)) else config
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    request_id=request_id or uuid.uuid4().hex
    resources=dict(config['resources'],replay=config['replay'],io_routes=config['io_routes'],
                   cube_args=config['cube_args'],replay_recipe=config['recipe'])
    recipe_path=output/'selected-replay.json';recipe_path.write_text(json.dumps(config['recipe'])+'\n')
    transport=config['transport']
    args=SimpleNamespace(output=output,request_id=request_id,recipe=recipe_path,
        runtime_root=Path(config.get('runtime_root','.')),cube_command=Path(__file__),
        ssh=transport['ssh'],identity=transport.get('identity'),replay_timeout=config.get('replay_timeout',240.))
    io=None;sequence=None;lock=None
    def check_cancel():
        if cancelled():raise KeyboardInterrupt('Operator cancelled combined reset')
    with configured(resources):
        try:
            check_cancel()
            key=hashlib.sha256(transport['ssh'].encode()).hexdigest()[:16]
            lock=(Path(tempfile.gettempdir())/('yam-tabletop-reset-'+key+'.lock')).open('a+')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError('Another reset owns this robot; no command requested')
            io=io_factory(args.ssh,args.identity,output/'transport',accept_late_frames=True,
                          worker_source=sequence_worker())
            io.before_request=check_cancel
            sequence=TabletopResetSequence(args,io=io,cube_program=cube_program or cube_main)
            result=sequence.run()
            return result
        except BaseException as exc:
            hold=None
            if io is not None:
                io.before_request=None
                try:
                    if getattr(io,'needs_reconnect',False):io.reconnect()
                    replay=io.call('replay_status')
                    if replay.get('request_id')==request_id and replay.get('running'):hold=io.call('replay_hold')
                except Exception as hold_error:hold=dict(unconfirmed=str(hold_error))
            failure=dict(state='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc),
                         request_id=request_id,hold=hold,timings={} if sequence is None else sequence.timings,
                         action='Inspect evidence; do not retry uncertain movement')
            for name in ('failure.json','result.json','status.json'):
                temporary=output/(name+'.writing');temporary.write_text(json.dumps(failure,indent=2)+'\n');os.replace(temporary,output/name)
            return failure
        finally:
            if io is not None:io.close()
            if lock is not None:lock.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--request-id')
    parser.add_argument('--cancel-file',type=Path)
    args=parser.parse_args(argv)
    stopped=threading.Event()
    def stop(*_args):stopped.set()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    result=run_reset(args.config,args.output,request_id=args.request_id,
                     cancelled=lambda:stopped.is_set() or bool(args.cancel_file and args.cancel_file.exists()))
    print(json.dumps(result),flush=True)
    return 0 if result.get('goals_reached') is True else 130 if result['state']=='cancelled' else 2
