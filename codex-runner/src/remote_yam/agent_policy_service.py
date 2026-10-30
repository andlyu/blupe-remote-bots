"""Separate Agent as Policy/MEMO worker; the local controller owns the lease."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from urllib import request
from urllib.parse import urlsplit
import uuid
from .providers import PolicyComplete


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class AgentPolicyService:
    supports_runtime_steering = True
    share_conversation = True

    def __init__(self, origin, token, *, robot_id, namespace, memo=True, model='gpt-6-astra'):
        target = urlsplit(origin)
        if (target.username or target.password or target.query or target.fragment
                or target.path not in ('', '/') or not target.hostname
                or not (target.scheme == 'https' or target.scheme == 'http' and target.hostname in ('127.0.0.1','localhost'))):
            raise ValueError('Agent worker requires HTTPS or a loopback origin')
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError('Agent worker credential is missing')
        self.origin, self._token = origin.rstrip('/'), token
        self.robot_id, self.namespace, self.memo, self.model = robot_id, namespace, memo, model
        self.provider_name = 'agent_as_policy_memo' if memo else 'agent_as_policy'
        self.display_name = 'Agent as Policy + MEMO' if memo else 'Agent as Policy'
        self.interaction_sink, self.steering = None, None
        self.cancelled, self.refresh_observation = lambda: False, None
        self._stop = threading.Event()
        self._open = request.build_opener(request.ProxyHandler({}), NoRedirect()).open
        self._client_id, self._run_id = uuid.uuid4().hex, None
        self._identity, self._pending, self._ack = None, None, None
        self._submitted, self._cursor = set(), -1
        self._summary = dict(enabled=memo, version=None, retrieved=[], saved=[])
        self._start_payload = None
        self.outcome = None
        self._settled_after = None

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, display_name=self.display_name,
                    memo=deepcopy(self._summary), implementation='runtime_coding_agent',
                    outcome=deepcopy(self.outcome), validation='agent_declared_not_independent_physical_validation')

    def configure_run_owner(self, namespace):
        if self._run_id is not None or not re.fullmatch(r'[a-f0-9]{64}', namespace):
            raise ValueError('Invalid agent memory owner')
        self.namespace = namespace

    def _request(self, path, payload=None):
        req = request.Request(self.origin + path,
            data=json.dumps(payload, allow_nan=False).encode() if payload is not None else None,
            headers={'Authorization':'Bearer ' + self._token, 'Content-Type':'application/json'})
        try:
            with self._open(req, timeout=5) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Worker response too large')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError('Worker response must be an object')
            return result
        except Exception:
            raise RuntimeError('Agent worker is unavailable; no motion was replayed') from None

    def validate_session_admission(self, api):
        health = self._request('/health')
        if health.get('robot_id') != self.robot_id:
            raise ValueError('Agent worker is configured for a different robot')

    def infer(self, *_):
        raise RuntimeError('Agent as Policy uses the packet provider interface')

    def build_trajectory(self, prompt, observation, first_step_id):
        if self._stop.is_set() or self.cancelled():
            raise RuntimeError('Agent run cancelled')
        identity = tuple(observation.get(k) for k in ('episode_id','lease_id'))
        if not all(identity) or self._identity is not None and identity != self._identity:
            raise RuntimeError('A new lease requires a new agent worker')
        if observation.get('step_id') != first_step_id or observation.get('settled') is not True:
            raise RuntimeError('Agent worker requires matching measured settled feedback')
        self._identity = identity
        if self._settled_after is None or self._ack is not None:
            self._settled_after = observation['observed_at']
        observation = dict(observation, settled_after=self._settled_after)
        if self._run_id is None:
            self._start_payload = dict(client_run_id=self._client_id, namespace=self.namespace,
                robot_id=self.robot_id, task=prompt, memo=self.memo, observation=observation)
            result = self._request('/runs', self._start_payload)
            if not re.fullmatch(r'[a-f0-9]{32}', result.get('id', '')):
                raise RuntimeError('Agent worker returned an invalid run')
            self._run_id = result['id']
        while not self._stop.is_set() and not self.cancelled():
            corrections = [dict(text=r['text'], request_id=r['request_id'])
                           for r in self.steering.snapshot() if r['state'] == 'queued'] if self.steering else []
            result = self._request('/runs/' + self._run_id + '/poll', dict(
                observation=observation, acknowledgement=self._ack, after=self._cursor, corrections=corrections))
            self._ack = None
            if self.steering:
                self.steering.acknowledge(result.get('delivered_corrections', []))
            for event in result.get('events', []):
                if event.get('id', -1) <= self._cursor:
                    continue
                self._cursor = event['id']
                if event.get('kind') == 'memory_retrieved':
                    self._summary.update(version=event.get('version'), retrieved=event.get('memory_ids', []), action=event.get('action'))
                elif event.get('kind') == 'memory_saved':
                    self._summary['saved'] = (self._summary['saved'] + [event.get('memory', {})])[-20:]
                if self.interaction_sink:
                    kind = event.get('kind')
                    message = str(event.get('message', ''))
                    if kind in ('assistant', 'agent_result'):
                        self.interaction_sink('model_response', message, response=message)
                    elif kind not in ('correction_queued', 'correction_delivered'):
                        if kind == 'tool_call':
                            message = ('MEMO' if event.get('arm') == 'memo' else 'Robot') + ' request: ' + message
                        elif kind == 'tool_result':
                            response = event.get('response') or {}
                            message = ('MEMO' if event.get('arm') == 'memo' else 'Robot') + ' result: ' + message
                            if response.get('execution'):
                                message += ' · measured completion'
                            elif response.get('ok') is False:
                                message += ' · ' + str(response.get('error_code', 'failed'))
                        self.interaction_sink('model_progress', message, progress_type='status')
            packet = result.get('packet')
            if packet:
                points = packet.get('points')
                if (packet.get('id') in self._submitted or not isinstance(points, list) or not points
                        or points[0].get('step_id') != first_step_id):
                    raise RuntimeError('Agent worker packet cursor or identity mismatch')
                self._pending = deepcopy(packet)
                self._submitted.add(packet['id'])
                return points
            if result.get('status') == 'completed':
                outcome = result.get('outcome') or {}
                if outcome.get('status') not in ('done', 'give_up'):
                    raise RuntimeError('Agent worker returned no valid task outcome')
                self.outcome = dict(outcome, reason=outcome.get('summary', 'Agent ended'))
                raise PolicyComplete(self.outcome.get('summary', 'Agent finished'))
            if result.get('status') in ('failed','stopped','interrupted'):
                raise RuntimeError('Agent worker ended before task completion')
            self._stop.wait(.1)
            if callable(self.refresh_observation) and self._ack is None:
                fresh = self.refresh_observation()
                if (tuple(fresh.get(k) for k in ('episode_id','lease_id')) != self._identity
                        or fresh.get('step_id') != first_step_id or fresh.get('settled') is not True):
                    raise RuntimeError('Fresh observation no longer matches this agent lease')
                observation = dict(fresh, settled_after=self._settled_after)
        raise RuntimeError('Agent run cancelled')

    def trajectory_completed(self, observation, waypoint_count):
        packet = self._pending
        if (not packet or waypoint_count != len(packet['points']) or observation.get('settled') is not True
                or observation.get('step_id') != packet['points'][-1]['step_id'] + 1):
            raise RuntimeError('Agent completion does not match its pending packet')
        self._ack, self._pending = packet['id'], None

    def trajectory_failed(self, *_args, **_kwargs):
        self.close_transport()

    def close_transport(self):
        self._stop.set()
        if self._run_id is not None:
            try:
                self._request('/runs/' + self._run_id + '/stop', {})
            except RuntimeError:
                pass


def configure(app, origin, token_file, model):
    """Administrator configuration; browser payloads cannot choose worker URLs."""
    app.agent_policy_public_config = {}
    if not origin and not token_file:
        return
    if not origin or not token_file:
        raise ValueError('Configure both YAM_AGENT_POLICY_ORIGIN and YAM_AGENT_POLICY_TOKEN_FILE')
    if app.hardware != 'yam':
        return
    token = Path(token_file).read_text().strip()
    for enabled in (False, True):
        name = 'agent_as_policy_memo' if enabled else 'agent_as_policy'
        def factory(selected_model, directory, enabled=enabled):
            if selected_model not in ('', model):
                raise ValueError('The agent model is configured by the server')
            namespace = uuid.uuid4().hex + uuid.uuid4().hex
            return AgentPolicyService(origin, token, robot_id=app.robot_id, namespace=namespace, memo=enabled, model=model)
        # Validate origin/token at setup, not after a visitor requests a run.
        factory(model, app.root)
        app.extra_providers[name] = factory
        app.agent_policy_public_config[name] = dict(label='Agent as Policy + MEMO' if enabled else 'Agent as Policy',
            model=model, help='The coding agent observes, programs, acts and checks. ' +
            ('MEMO retrieves prior corrections and saves generalized skills. ' if enabled else 'Skillbook reuse is off. ') +
            'Send corrections in task chat; use Stop to halt. Saved skills are agent-authored and unverified.')


def memory_identity(app, cookies, visitor):
    """Opaque, HttpOnly browser capability; no account or personal data needed."""
    name = app.cookie_name + '-memory'
    cookie = cookies.get(name)
    value = cookie.value if cookie else ''
    if not re.fullmatch(r'[a-f0-9]{64}', value):
        value = uuid.uuid4().hex + uuid.uuid4().hex
    visitor.agent_memory_namespace = hashlib.sha256((app.robot_id + ':' + value).encode()).hexdigest()
    header = name + '=' + value + '; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000'
    if app.secure:
        header += '; Secure'
    return (b'set-cookie', header.encode())
