"""Client for configured local Playground policies, using existing visitor auth."""
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


class RunnerPolicyClient:
    def __init__(self, origin='http://127.0.0.1:8787', robot_id='yam-1', *, timeout=30, transport_origin=None):
        parsed=urlsplit(origin)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment
                or parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1')):
            raise ValueError('Use a trusted HTTPS runner origin or a loopback HTTP runner/tunnel')
        self.origin=origin.rstrip('/');self.robot_id=robot_id;self.timeout=timeout
        self.transport_origin=(transport_origin or self.origin).rstrip('/')
        transport=urlsplit(self.transport_origin)
        if (transport.scheme not in ('http','https') or not transport.hostname or transport.username or transport.password
                or transport.path not in ('','/') or transport.query or transport.fragment
                or transport.scheme=='http' and transport.hostname not in ('127.0.0.1','localhost','::1')):
            raise ValueError('Use a trusted HTTPS or loopback transport')
        self.jar=CookieJar();self.opener=build_opener(HTTPCookieProcessor(self.jar))
        self.csrf='';self.cookie='';self.attempt_id=None;self.metadata=None

    def _request(self,path,payload=None):
        headers={'Origin':self.origin,'Host':urlsplit(self.origin).netloc,'X-Blupe-Robot':self.robot_id}
        if self.cookie:headers['Cookie']=self.cookie
        data=None
        if payload is not None:
            headers.update({'Content-Type':'application/json','X-Yam-Runner-Token':self.csrf})
            data=json.dumps(payload).encode()
        # Writes are deliberately attempted once. An uncertain start must be
        # reconciled with status through this same visitor, never auto-retried.
        with self.opener.open(Request(self.transport_origin+path,data=data,headers=headers),timeout=self.timeout) as response:
            return json.load(response)

    def connect(self):
        self.metadata=self._request('/api/session',{})
        self.csrf=self.metadata['csrf']
        cookies='; '.join(cookie.name+'='+cookie.value for cookie in self.jar)
        if cookies:self.cookie=cookies
        return self.metadata

    def start(self,policy='reset_bin',*,runner_name='API operator',run_duration_s=600,prompt=None):
        metadata=self.metadata or self.connect()
        spec=metadata.get('configured_providers',{}).get(policy)
        if not spec:
            raise ValueError('Policy is not installed for this robot: '+policy)
        task=spec.get('task') or prompt
        if not task:raise ValueError('This configured policy requires a prompt')
        result=self._request('/api/run',dict(provider=policy,model=spec['model'],prompt=task,
                            runner_name=runner_name,run_duration_s=run_duration_s))
        self.attempt_id=result['attempt_id']
        return result

    def status(self):
        result=self._request('/api/status')
        if self.attempt_id and result.get('attempt_id')!=self.attempt_id:
            raise RuntimeError('Visitor now refers to a different run; do not control it with this handle')
        return result

    def stop(self):
        self.status()  # Validate the retained visitor/attempt before cancellation.
        return self._request('/api/stop',{})

    def save(self,path):
        """Persist the visitor capability for later status/Stop, private mode0600."""
        data=dict(schema='blupe-runner-policy-client-v1',origin=self.origin,transport_origin=self.transport_origin,robot_id=self.robot_id,
                  cookie=self.cookie,csrf=self.csrf,attempt_id=self.attempt_id)
        flags=os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0)
        fd=os.open(Path(path),flags,0o600)
        with os.fdopen(fd,'w') as stream:
            os.fchmod(stream.fileno(),0o600)
            json.dump(data,stream)
            stream.write('\n')

    @classmethod
    def load(cls,path):
        data=json.loads(Path(path).read_text())
        if data.get('schema')!='blupe-runner-policy-client-v1':raise ValueError('Unknown runner session file')
        client=cls(data['origin'],data['robot_id'],transport_origin=data.get('transport_origin'))
        client.cookie=data['cookie'];client.csrf=data['csrf'];client.attempt_id=data.get('attempt_id')
        return client
