"""One-shot requests to an existing primary Replay owner; never a motor driver."""
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request


class ReplayTransport:
    def __init__(self,config):
        self.config=config
        self.origin=config['controller_origin'].rstrip('/')

    def read(self,path):
        with urllib.request.urlopen(self.origin+path,timeout=8) as response:return json.load(response)

    def operation(self,name,payload=None):
        if name=='replay_status':return self.read('/api/replay/status')
        path={'replay_start':'/api/replay/start','replay_hold':'/api/replay/hold'}[name]
        headers={'Content-Type':'application/json'}
        try:manifest=self.read('/api/capabilities')
        except urllib.error.HTTPError as exc:
            legacy=self.config.get('legacy_contract')
            if exc.code!=404 or not legacy:raise
            files=legacy.get('source_sha256',{})
            if not files:raise ValueError('Legacy Replay requires explicit qualified source identities')
            for filename,expected in files.items():
                if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=expected:
                    raise ValueError('Qualified Replay source changed; no operation sent')
            status=self.read('/api/replay/status')
            if not all(status.get(key)==value for key,value in legacy['status'].items()):
                raise ValueError('Qualified Replay contract changed; no operation sent')
        else:
            if manifest.get('interface')!={'name':'yam-operator','version':1} or not manifest.get('instance_id'):
                raise ValueError('Controller interface mismatch; no operation sent')
            if not any(op.get('method')=='POST' and op.get('path')==path for op in manifest.get('operations',[])):
                raise ValueError('Replay operation is not advertised; no operation sent')
            headers.update({'X-YAM-Interface-Version':'1','X-YAM-Controller-Instance':manifest['instance_id']})
        if name=='replay_start':payload=dict(payload,edited=True,execution_policy='controller-faults')
        request=urllib.request.Request(self.origin+path,data=json.dumps(payload or {}).encode(),headers=headers)
        # Exactly one POST. Lost acknowledgements must never replay a movement.
        with urllib.request.urlopen(request,timeout=8) as response:result=json.load(response)
        if result.get('ok') is False or result.get('error'):raise RuntimeError(result.get('error') or 'Replay refused')
        return result
