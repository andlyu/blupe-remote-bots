"""Gemini's attributed, no-email admission through the canonical robot queue.

Only session creation changes: the same client still owns capabilities, FIFO,
leases, Home, packet validation, feedback and Stop. No fallback to the ordinary
email-producing creation endpoint is allowed, including after API rollback.
"""
import re

from station_inputs import API_ORIGIN, transport_classes

HttpSessionAPI,_CameraSource=transport_classes()
from remote_yam.session import SessionAPIError

QUIET_PATH='/v1/sessions/no-email'


class GeminiSessionAPI(HttpSessionAPI):
    def __init__(self,runner_name,email,*,timeout_s=5,websocket_factory=None):
        if not isinstance(runner_name,str) or not runner_name.strip() or len(runner_name.strip())>32 or any(ord(c)<32 or ord(c)==127 for c in runner_name):
            raise ValueError('The existing queue requires an actual runner name of at most32characters')
        if runner_name.strip().lower() in {'anonymous','autonomous','automated'}:
            raise ValueError('Execution mode is separate from the actual runner name')
        if not isinstance(email,str) or len(email.strip())>254 or any(ord(c)<32 or ord(c)==127 for c in email) or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email.strip()) is None:
            raise ValueError('The existing queue requires the confirmed valid runner email')
        self.runner_name,self.email=runner_name.strip(),email.strip()
        super().__init__(API_ORIGIN,timeout_s=timeout_s,websocket_factory=websocket_factory,
                         supports_trajectories=True,robot_id='yam-1')

    def create_session(self,prompt,run_duration_s=300,*,provider='',cadence_hz=10.):
        return super().create_session(prompt,run_duration_s,runner_name=self.runner_name,
            email=self.email,model='Gemini Robotics',email_run_video=False,
            provider=provider,cadence_hz=cadence_hz)

    def _request(self,method,path,payload=None,*,bearer=None):
        if method=='POST' and path=='/v1/sessions':
            contracts=super()._request('GET','/v1/contracts')
            quiet=contracts.get('session_create_no_email',{})
            properties=quiet.get('properties',{}) if isinstance(quiet,dict) else None
            if (not isinstance(quiet,dict) or not isinstance(properties,dict)
                    or quiet.get('x-http-path')!=QUIET_PATH or quiet.get('x-http-method')!='POST'
                    or not all(isinstance(properties.get(field),dict)
                               and properties[field].get('type')=='boolean'
                               and properties[field].get('const') is False
                               for field in ('email_queue_alert','email_run_video'))):
                raise SessionAPIError('No-email queue admission is unavailable; no session was created',
                                      code='no_email_queue_unavailable',status=503)
            payload={**payload,'email_queue_alert':False,'email_run_video':False}
            path=QUIET_PATH
        return super()._request(method,path,payload,bearer=bearer)
