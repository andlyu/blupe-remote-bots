"""Host-owned execution receipts, outside the generated-code job mount.

These bind source/inputs/output to one container execution. They do not certify
MuJoCo's model accuracy, controller intent or a physical/object task outcome.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import uuid

LIMITS = {'controller.py':160000, 'station.json':64000, 'report.json':64000,
          'simulation.mp4':128*1024*1024, 'commands.json':16*1024*1024,
          'simulation.log':64000}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_private(path, data):
    """Replace an owned job filename without following links or opening FIFOs."""
    fd,temp=tempfile.mkstemp(prefix='.gemini-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as file:file.write(data)
        os.replace(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)


def read_regular(path, limit):
    """Never follow generated symlinks, block on FIFOs or read unbounded data."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Expected bounded regular artifact: ' + path.name)
        data = file.read(limit+1)
    if len(data)>limit:
        raise ValueError('Artifact exceeded its bound: ' + path.name)
    return data


def input_snapshot(workspace, variant='yam1'):
    names=['controller.py']
    if variant=='yam1' or (workspace/'station.json').exists():names.append('station.json')
    return {name:read_regular(workspace/name,LIMITS[name]) for name in names}


def retain_execution(workspace, before, *, image, variant, exit_code, log,
                     cleanup_confirmed, execution_id=None):
    """Copy actual outputs only after the executor confirms container removal.

    Preserve failed/mismatched attempts too. A later tool/controller write can
    change the job mount; it cannot replace these originals or their hashes.
    """
    if not cleanup_confirmed:
        raise RuntimeError('Simulation cleanup is unverified; no handoff accepted')
    execution_id = uuid.UUID(execution_id).hex if execution_id else uuid.uuid4().hex
    bundle = workspace.parent/'simulation-evidence'/workspace.name/execution_id
    bundle.mkdir(parents=True,mode=0o700,exist_ok=False)
    blobs = dict(before)
    problems = []
    for name in before:
        try:
            if read_regular(workspace/name,LIMITS[name]) != before[name]:
                problems.append('Simulation changed '+name+' after launch')
        except (OSError,ValueError):
            problems.append('Simulation input is missing or invalid: '+name)
    for name in ('report.json','simulation.mp4','commands.json'):
        try:blobs[name] = read_regular(workspace/name,LIMITS[name])
        except (OSError,ValueError):
            if name != 'commands.json':problems.append('Simulation output is missing or invalid: '+name)
    blobs['simulation.log'] = log.encode(errors='replace')[-LIMITS['simulation.log']:]
    report = None
    try:
        report = json.loads(blobs['report.json'])
        if not isinstance(report,dict):raise ValueError()
        if (report.get('controller_sha256') != digest(before['controller.py'])
                or 'station.json' not in before
                or report.get('station_snapshot_sha256') != digest(before['station.json'])):
            problems.append('Simulation report does not match the launched controller and station')
        if report.get('controller_completed') is not True or report.get('error') is not None:
            problems.append('Simulation controller did not complete')
        if report.get('physical') is not False:
            problems.append('Simulation report has inconsistent execution mode')
    except (KeyError,ValueError,TypeError):
        problems.append('Simulation report is unreadable')
    if exit_code != 0:problems.append('Simulation process did not exit successfully')
    if variant != 'yam1':problems.append('Execution is not the selected YAM1 variant')
    records=[]
    for name,data in blobs.items():
        fd=os.open(bundle/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as file:file.write(data)
        records.append(dict(name=name,bytes=len(data),sha256=digest(data)))
    receipt=dict(id=execution_id,created_at=time.time(),image=image,variant=variant,
                 exit_code=exit_code,cleanup_confirmed=True,binding_passed=not problems,
                 rejections=problems,controller_sha256=digest(before['controller.py']),
                 station_snapshot_sha256=digest(before['station.json']) if 'station.json' in before else None,artifacts=records,
                 scope='Source/input/replay binding only; task success and physical operation unverified')
    data=(json.dumps(receipt,indent=2)+'\n').encode()
    (bundle/'execution.json').write_bytes(data)
    os.chmod(bundle/'execution.json',0o600)
    receipt['artifacts']=[*records,dict(name='execution.json',bytes=len(data),sha256=digest(data))]
    return receipt,report


def current_controller_matches(workspace, receipt):
    if not receipt or not receipt.get('binding_passed'):
        return False
    try:
        return all(digest(read_regular(workspace/name,LIMITS[name]))==receipt[key]
                   for name,key in (('controller.py','controller_sha256'),('station.json','station_snapshot_sha256')))
    except (OSError,ValueError,KeyError):
        return False
