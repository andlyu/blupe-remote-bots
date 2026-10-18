"""Reusable configured cube-only reset; the existing cube CLI owns hardware."""
from contextlib import suppress
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import threading
import uuid

from .station import configured


def save(path, value):
    temporary = path.with_suffix('.writing')
    temporary.write_text(json.dumps(value, allow_nan=False) + '\n')
    temporary.replace(path)


def run_cube_reset(config, output, *, request_id=None, cube_main=None):
    """Fresh output/request identity, no Replay and no extra replay Home."""
    if cube_main is None:
        from .cube_cli import main as cube_main
    config = json.loads(Path(config).read_text()) if isinstance(config, (str, Path)) else config
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    request_id = request_id or uuid.uuid4().hex
    argv = list(config['cube_args'])
    if '--after-replay' in argv or '--resume-plan' in argv:
        raise ValueError('Cube-only configuration cannot resume an earlier request')
    argv = [value for value in argv if value != '--home-after-replay']
    argv += ['--output', str(output / 'cube-reset'), '--ssh', config['transport']['ssh'],
             '--identity', config['transport'].get('identity') or '', '--accept-late-frames']
    resources = dict(config['resources'], io_routes=config['io_routes'], replay=config['replay'],
                     cube_args=config['cube_args'], replay_recipe=config['recipe'])
    key = hashlib.sha256(config['transport']['ssh'].encode()).hexdigest()[:16]
    lock = (Path(tempfile.gettempdir()) / ('yam-tabletop-reset-' + key + '.lock')).open('a+')
    finished = threading.Event()
    prior_signal = signal.getsignal(signal.SIGTERM)
    result, code = None, 2
    def progress():
        while not finished.wait(.25):
            with suppress(OSError, ValueError, IndexError):
                events = json.loads((output / 'cube-reset/events.json').read_text())
                event = events[-1]
                save(output / 'status.json', dict(request_id=request_id, phase='cube_reset',
                    state=event.get('event', 'running'), color=event.get('color')))
    thread = threading.Thread(target=progress, daemon=True)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save(output / 'status.json', dict(request_id=request_id, phase='preflight', state='preparing'))
        save(output / 'invocation.json', dict(request_id=request_id, argv=argv,
            entrypoint='remote_yam.resets.cube_cli.main', replay_requested=False))
        thread.start()
        with configured(resources):
            code = cube_main(argv)
    except KeyboardInterrupt:
        code = 130
        result = dict(state='cancelled', goals_reached=False)
    except Exception as exc:
        result = dict(state='failed', goals_reached=False, error=str(exc))
    finally:
        finished.set()
        if thread.ident is not None:
            thread.join(1)
        signal.signal(signal.SIGTERM, prior_signal)
        lock.close()
    if result is None:
        try:
            result = json.loads((output / 'cube-reset/result.json').read_text())
        except (OSError, ValueError):
            result = dict(state='failed', goals_reached=False, error='Cube CLI ended without a terminal receipt')
    result.update(request_id=request_id, replay_requested=False, cube_cli_exit_code=code)
    save(output / 'result.json', result)
    save(output / 'status.json', dict(request_id=request_id, phase=result['state'], state=result['state']))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request-id')
    args = parser.parse_args(argv)
    result = run_cube_reset(args.config, args.output, request_id=args.request_id)
    print(json.dumps(result), flush=True)
    return 0 if result.get('goals_reached') and result['cube_cli_exit_code'] == 0 else 130 if result['state'] == 'cancelled' or result['cube_cli_exit_code'] == 130 else 2


if __name__ == '__main__':
    raise SystemExit(main())
