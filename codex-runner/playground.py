"""Shared browser playground. Hosting products extend its application hooks."""
from __future__ import annotations

import hashlib
import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from http.cookies import SimpleCookie, CookieError
import json
import math
import os
import re
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit, parse_qs
from urllib import request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from remote_yam.submission_log import SubmissionLog, LoggedSessionAPI
from remote_yam.cameras import CameraFrameSource, CAMERA_NAMES, NoRedirect
from remote_yam.controller import RunnerController
from remote_yam.interactions import list_recordings, read_recording
from remote_yam.socials import social_handles, save_handles
from remote_yam.artifacts import log_archive, run_artifacts
from remote_yam.providers import RepeatingRaiseLowerAdapter
from remote_yam.robocurve_policy import OpenAIAdapter, AstraAdapter
from remote_yam.session import HttpSessionAPI, MockSessionAPI
from remote_yam.reactions import Reactions, EMOJIS

ACTIVE = {"queued", "preparing", "running"}
COOKIE = "__Host-yam-visitor"
LIVE_VIEWER_SECONDS = 30


def model_display_name(provider):
    """Name the public conversation panel shows for the model driving the run."""
    provider = provider if isinstance(provider, dict) else {}
    name, model = provider.get("provider"), str(provider.get("model") or "")
    if provider.get("display_name"):
        return str(provider["display_name"])[:100]
    if name in {"claude", "anthropic"}:
        match = re.match(r'claude-(opus|sonnet|haiku|fable)-(\d+)(?:-(\d{1,2})(?!\d))?', model)
        if match:
            return match[1].title() + ' ' + match[2] + ('.' + match[3] if match[3] else '')
        return model or "Claude"
    return {"groot": "GR00T", "molmoact2": "MolmoAct2", "dreamzero": "DreamZero", "local_raise_lower": "Built-in policy"}.get(name,
        'Astra' if not model or model == 'gpt-6-astra' else model)


class RequestError(Exception):
    def __init__(self, status: int, message: str, *, setup=None):
        self.status, self.message = status, message
        self.setup = setup


class HostedSessionAPI(HttpSessionAPI):
    def open_events(self, session_id):
        try:
            return super().open_events(session_id)
        except Exception:
            # create_session has already returned a capability. If attaching the
            # stream fails, remove this known queue entry before losing its ID.
            with suppress(Exception):
                self.stop_session(session_id)
            raise


class EphemeralController(RunnerController):
    """Release the adapter's retained credential after every worker exit."""
    def forget_key(self):
        self._stop_event.set()
        with self._lock:
            if self._provider is not None and hasattr(self._provider, "_api_key"):
                self._provider._api_key = ""
            close = getattr(self._provider, 'close_transport', None)
            if callable(close):
                with suppress(Exception):
                    close()

    def busy(self):
        with self._lock:
            return self._worker is not None and self._worker.is_alive()

    def _run_loop(self, max_steps):
        try:
            super()._run_loop(max_steps)
        finally:
            self.forget_key()


@dataclass
class Visitor:
    controller: EphemeralController
    directory: Path
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    born: float = field(default_factory=time.monotonic)
    touched: float = field(default_factory=time.monotonic)
    last_launch: float = -float("inf")
    launch_requested_at: float | None = None
    chat_id: str = field(default_factory=lambda: secrets.token_hex(4))
    last_chat: float = -float("inf")
    last_data_chat: float = -float("inf")
    data_chat_busy: bool = False
    last_reaction: float = -float("inf")
    last_stream_report: float = -float("inf")
    last_watched: float = -float("inf")
    runner_task: str = ""
    runner_name: str = "Anonymous"
    runner_session_id: str | None = None
    episode_ids: set[str] = field(default_factory=set)
    launches: int = 0
    saved_keys: dict[str, str] = field(default_factory=dict, repr=False)
    subscription_prompts: dict[str, str] = field(default_factory=dict)
    visitor_chat: object | None = field(default=None, repr=False)
    retired: bool = False
    retain_recordings: bool = False
    assessment_session: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def close(self):
        with self.lock:
            self.retired = True
            self.saved_keys.clear()
            self.episode_ids.clear()
            self.visitor_chat = None
            self.controller.forget_key()
            self.controller.disconnect("web_session_ended")
        # A cancelled provider HTTP request may take up to its transport timeout
        # to return. Do not remove its journal directory while it can still write.
        worker = self.controller._worker
        if worker is not None:
            worker.join(timeout=50)
        if not self.retain_recordings and not self.controller.busy():
            shutil.rmtree(self.directory, ignore_errors=True)


class HostedRunner:
    def __init__(self, *, public_origin: str, session_api: str | None,
                 camera_origin: str, astra_endpoint: str = "",
                 hardware_control: bool = False, development: bool = False,
                 max_sessions: int = 32, idle_seconds: float = 1800,
                 lifetime_seconds: float = 7200, api_factory=None,
                 provider_factory=None, api_depth_provider_factory=None, use_api_depth=False, extra_providers=None, chat_database=None, share_conversation=True,
                 groot_key_file="", groot_config=None, runpod_key_file="", runpod_config=None, dream_credentials_file="", dream_python="", dream_worker_pool=None, dream_worker_factory=None, dream_worker_ready=None, local_codex=False, local_claude=False, default_provider="openai", robots=None, robot_id="yam-1", camera_names=CAMERA_NAMES, joint_counts=(6,6), hardware=None, policy_camera_names=None, recording_root=None, operator_status_origin=None):
        parsed = urlsplit(public_origin)
        if (not parsed.hostname or parsed.path not in {"", "/"} or parsed.query
                or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("YAM_WEB_ORIGIN must be an origin without a path or credentials")
        if parsed.scheme != "https" and not (
                development and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise ValueError("Public hosting requires HTTPS; HTTP is limited to explicit localhost development")
        if not session_api and not development:
            raise ValueError("YAM_SESSION_API is required outside localhost development")
        if astra_endpoint:
            endpoint = urlsplit(astra_endpoint)
            if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError("The configured Astra endpoint must use HTTPS without credentials or a query")
        self.joint_counts = tuple(joint_counts)
        self.hardware = hardware or ('so101' if self.joint_counts == (5,0) else 'yam' if self.joint_counts == (6,6) else 'custom')
        if self.hardware == 'bimanual_so101' and self.joint_counts != (5,5):
            raise ValueError('Bimanual SO101 requires five joints per arm')
        if self.hardware == 'makerarm' and self.joint_counts != (6,0):
            raise ValueError('MakerArm requires joint_counts [6,0]')
        self.camera_names = tuple(camera_names)
        self.policy_camera_names = tuple(policy_camera_names) if policy_camera_names is not None else self.camera_names
        if not self.policy_camera_names or not set(self.policy_camera_names).issubset(self.camera_names):
            raise ValueError("Policy cameras must be selected from the robot cameras")
        self.robot_id = robot_id
        from remote_yam.video_stream import video_stream
        self.video_stream = video_stream(robot_id)
        self.robots = robots if robots is not None else [
            {"id": robot_id, "name": "YAM", "url": public_origin.rstrip("/") + "/"}]
        ids = set()
        for robot in self.robots:
            url = urlsplit(robot["url"])
            local = development and url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}
            if (not robot.get("id") or robot["id"] in ids or not robot.get("name")
                    or not url.hostname or (url.scheme != "https" and not local)
                    or url.username or url.password or url.fragment):
                raise ValueError("Robots need unique IDs, names, and HTTPS dashboard URLs")
            ids.add(robot["id"])
        if robot_id not in ids:
            raise ValueError("Current robot must be included in the dashboard robot list")
        self.origin = public_origin.rstrip("/")
        if local_codex and not (development and parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'}):
            raise ValueError('Codex subscription access is restricted to the local runner')
        if local_claude and not (development and parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'}):
            raise ValueError('Claude subscription access is restricted to the local runner')
        self.groot_config = dict(groot_config or {})
        self.groot_model = self.groot_config.get('model', 'groot-reviewed-step10000')
        self.groot_label = self.groot_config.get('label', 'GR00T')
        self.groot_key_file = groot_key_file if robot_id in self.groot_config.get('robot_ids', ['yam-1']) and self.hardware == "yam" else ""
        self.local_codex = local_codex
        self.local_claude = local_claude
        self.default_provider = default_provider
        self.authority = parsed.netloc
        self.secure = parsed.scheme == "https"
        self.simulation = not session_api
        self.cookie_name = COOKIE if self.secure else "yam-local-visitor"
        if robot_id != "yam-1":
            import hashlib
            self.cookie_name += "-" + hashlib.sha256(robot_id.encode()).hexdigest()[:16]
        self.astra_endpoint = astra_endpoint
        self.hardware_control = hardware_control
        self.max_sessions = max_sessions
        self.idle_seconds, self.lifetime_seconds = idle_seconds, lifetime_seconds
        self.api_factory = api_factory or (lambda: HostedSessionAPI(session_api, supports_trajectories=True, robot_id=robot_id, joint_counts=self.joint_counts) if session_api else MockSessionAPI())
        self.share_conversation = share_conversation
        self.provider_factory = provider_factory
        self.api_depth_provider_factory = api_depth_provider_factory
        self.use_api_depth = use_api_depth
        self.extra_providers = dict(extra_providers or {})
        self.camera_source = CameraFrameSource(camera_origin, camera_names=self.camera_names)
        self.runpod_providers = {}
        if runpod_key_file and robot_id == 'yam-1' and self.hardware == 'yam' and self.joint_counts == (6, 6):
            from remote_yam.yam_runpod_policy import YAMRunpodAdapter, MODELS
            if not {'top', 'left', 'right'}.issubset(self.camera_names):
                raise ValueError('YAM1 joint policies require all three camera roles')
            for name, spec in (runpod_config or {}).items():
                if name not in MODELS or not isinstance(spec, dict) or not spec.get('endpoint'):
                    raise ValueError('Invalid YAM1 RunPod policy configuration')
                selected = MODELS[name]
                def factory(model, directory, name=name, endpoint=spec['endpoint'], selected=selected):
                    if model not in ('', selected['model']):
                        raise RequestError(400, 'Unknown YAM1 checkpoint')
                    return YAMRunpodAdapter(Path(runpod_key_file).expanduser().read_text().strip(),
                        provider=name, endpoint=endpoint, robot_id=self.robot_id,
                        camera_source=CameraFrameSource(camera_origin, camera_names=('top', 'left', 'right')))
                self.extra_providers[name] = factory
                self.runpod_providers[name] = dict(label=selected['label'], model=selected['model'],
                    default_run_duration_s=120,
                    help='YAM1 joint policy using the overhead and wrist cameras. GPU preparation can take several minutes.')
        from remote_yam.run_data_chat import OpenAIDataChat
        self.data_chat = OpenAIDataChat.configured()
        self.visitors: dict[str, Visitor] = {}
        self.monitor_api = self.api_factory()
        self.dream_providers = {}
        self.dream_worker_ready = dream_worker_ready or (lambda: True)
        if dream_credentials_file and dream_python and self.hardware == 'yam' and self.joint_counts == (6, 6):
            from remote_yam.dream_policy import DreamAdapter, DreamWorker, MODELS
            from remote_yam.controller_workspace import workspace_for_robot
            workspace = workspace_for_robot(self.robot_id)
            gateway_step = None
            if workspace:
                limits = workspace._safety()
                gateway_step = math.degrees(min(limits['max_adjacent_delta_rad'],
                                                limits['max_joint_velocity_rad_s'] / 10))
            if not Path(dream_credentials_file).expanduser().is_file():
                raise ValueError('Configured Dream credentials file is missing')
            if not {'top', 'left', 'right'}.issubset(self.camera_names):
                raise ValueError('Dream requires all three YAM camera roles')
            for name, (checkpoint, label) in MODELS.items():
                def factory(model, directory, name=name, checkpoint=checkpoint):
                    if not self.dream_worker_ready():
                        raise RequestError(503, 'Dream is preparing; please retry shortly')
                    if model not in ('', checkpoint):
                        raise RequestError(400, 'Unknown Dream checkpoint')
                    return DreamAdapter(provider=name, model=checkpoint, credentials=dream_credentials_file,
                        python=dream_python, directory=Path(directory) / 'dream-sdk',
                        camera_source=CameraFrameSource(camera_origin, camera_names=('top', 'left', 'right')),
                        observation_source=lambda: self.monitor_api.get_robot_observation(self.robot_id),
                        gateway_max_step_deg=gateway_step,
                        worker_pool=dream_worker_pool,
                        worker_factory=dream_worker_factory or DreamWorker,
                        robot_id=self.robot_id)
                self.extra_providers[name] = factory
                self.dream_providers[name] = {'label': label, 'model': checkpoint,
                    'default_run_duration_s': 120, 'max_run_duration_s': 1200,
                    'motion_cap': {'default_step_deg': 20, 'gateway_step_deg': gateway_step},
                    'help': 'Dream-1 follows your instruction using the overhead and wrist cameras. Runs until the time limit or Stop.'}
        self.observation = None
        self.queue = None
        self.operator_auto_queue = None
        self.operator_status_origin = operator_status_origin
        from remote_yam.past_runs import PastRuns
        from remote_yam.run_history import run_models
        self.past_runs = PastRuns(robot_id=None, model_reader=lambda: run_models(self.submission_log.path))
        self.task = None
        self.cleanups = set()
        self.frame_cache = {}
        self.frame_locks = {name: threading.Lock() for name in self.camera_names}
        self.retain_recordings = recording_root is not None
        if self.retain_recordings and not (development and parsed.hostname == "127.0.0.1"):
            raise ValueError("Durable station recordings require loopback hosting")
        self.root = Path(recording_root).expanduser().resolve() if self.retain_recordings else Path(tempfile.mkdtemp(prefix="yam-web-"))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        metadata_root = self.root if self.retain_recordings else ROOT / "data"
        from remote_yam.chat_history import ChatHistory
        self.chat_history = ChatHistory(chat_database or self.root / "chat.sqlite3")
        self.reactions = Reactions()
        self.social_database = Path(os.environ.get('YAM_SOCIAL_DATABASE', metadata_root / 'run-socials.sqlite3'))
        from remote_yam.past_runs import RunNames
        self.run_names = RunNames(os.environ.get('YAM_RUN_NAMES_DATABASE', metadata_root / 'run-names.sqlite3'))
        self.submission_log = SubmissionLog(os.environ.get("YAM_SUBMISSION_DATABASE", metadata_root / "queue-submissions.sqlite3"))
        from remote_yam.run_assessments import RunAssessments
        from remote_yam.task_cloud import TaskCloud
        self.run_assessments = RunAssessments(os.environ.get('YAM_ASSESSMENT_DATABASE', metadata_root / 'run-assessments.sqlite3'))
        self.task_cloud = TaskCloud(os.environ.get('YAM_TASK_CLOUD_DATABASE', metadata_root / 'task-cloud.sqlite3'))
        self.remembered_names = set()

    async def public_extension(self, scope, receive, send, headers):
        """Optional application endpoints; Host is checked, visitor auth is not."""
        return False

    async def session_extension(self, cookies, visitor):
        """Additional session metadata/headers; Origin and JSON are checked."""
        return {}, []

    async def action_extension(self, path, visitor, payload, cookies, send):
        """Optional actions after visitor, Origin and CSRF validation."""
        return False

    async def chat_setup(self, visitor):
        return {'reaction_cursor':self.reactions.cursor, 'chat_scope':'runner'}

    async def chat_snapshot(self, visitor):
        return {'messages':await asyncio.to_thread(self.chat_history.messages),
                'visitor':visitor.chat_id, 'reactions':self.reactions.snapshot(),
                'server_time':time.time()}

    async def append_chat(self, visitor, name, text):
        await asyncio.to_thread(self.chat_history.append, visitor.chat_id, name, text)

    async def publish_reaction(self, visitor, emoji):
        return self.reactions.publish(emoji, visitor.chat_id)

    def validate_launch(self, visitor, payload, paid):
        """Application admission rules, before shared robot/provider validation."""

    def page(self):
        return (ROOT / "static/hosted.html").read_bytes()

    def remember_runner(self, visitor):
        state = visitor.controller.status()
        eid = state.get('episode_id')
        if eid and visitor.runner_session_id and state.get('session_id') == visitor.runner_session_id:
            visitor.episode_ids.add(eid)
            try:
                self.run_names.remember_metadata(eid, self.robot_id, visitor.runner_task, state.get("run_started_at"), state.get("run_configuration"))
                self.run_names.remember_result(eid, state)
            except (OSError, sqlite3.Error):
                pass
        if eid and eid not in self.remembered_names and state.get('session_id') == visitor.runner_session_id:
            # History storage must never prevent Stop or other robot controls.
            try:
                self.run_names.remember(eid, visitor.runner_name)
            except (OSError, sqlite3.Error):
                return
            self.remembered_names.add(eid)

    def assessment_user(self, visitor):
        """Hosting hook: return an existing recorded account ID, never request identity.

        Applications may set recorded_user_id after their existing authentication.
        It is never read from assessment request JSON or sent to public clients.
        """
        return getattr(visitor, 'recorded_user_id', None)

    def remember_assessment_owner(self, visitor):
        """Run in maintenance/read paths; never add overlay I/O before Stop."""
        state = visitor.controller.status()
        eid = state.get('episode_id')
        if eid and visitor.runner_session_id and state.get('session_id') == visitor.runner_session_id:
            self.run_assessments.register(eid, visitor.assessment_session, self.assessment_user(visitor),
                ended=state.get('status') not in ACTIVE | {'idle'})

    def new_visitor(self):
        if len(self.visitors) >= self.max_sessions:
            raise RequestError(503, "All browser sessions are busy. Please try again shortly.")
        capability = secrets.token_urlsafe(32)
        directory = self.root / ("recordings" if self.retain_recordings else secrets.token_hex(16))
        directory.mkdir(mode=0o700, exist_ok=self.retain_recordings)
        visitor = Visitor(EphemeralController(
            LoggedSessionAPI(self.api_factory(), self.submission_log), hardware_control_enabled=self.hardware_control,
            recording_root=directory, robot_id=self.robot_id, joint_counts=self.joint_counts,
            share_conversation=self.share_conversation), directory, retain_recordings=self.retain_recordings)
        self.visitors[capability] = visitor
        return capability, visitor

    def model_camera_names(self):
        if self.joint_counts == (5,5) and self.hardware != 'makerarm':
            from remote_yam.bimanual_so101_policy import BimanualSO101PolicyMixin
            return BimanualSO101PolicyMixin.model_camera_names(self.policy_camera_names)
        if self.joint_counts == (5,0) and self.hardware != 'makerarm':
            return ('front',)
        return self.camera_names

    def robot_connected(self, robot_id):
        peer = getattr(self, '_fleet_apps', {}).get(robot_id, self if robot_id == self.robot_id else None)
        if peer is None or time.monotonic() - getattr(peer, 'queue_observed_at', 0) > 10:
            return None
        queue = getattr(peer, 'queue', None)
        if not isinstance(queue, dict):
            return None
        station = next((s for s in queue.get('stations', []) if s.get('jetson_id') == robot_id), None)
        return bool(station.get('connected')) if station else False

    def refresh_monitor(self):
        from remote_yam.operator_status import read_auto_queue
        self.operator_auto_queue = (read_auto_queue(self.operator_status_origin) if self.operator_status_origin else read_auto_queue()) if self.hardware_control and self.robot_id == "yam-1" else None
        try:
            self.observation = self.monitor_api.get_robot_observation(self.robot_id)
        except Exception:
            self.observation = None
        try:
            self.queue = self.monitor_api.get_queue_snapshot()
            self.queue_observed_at = time.monotonic()
        except Exception:
            self.queue = None

    def camera_frame(self, name, url):
        # Share a short-lived frame between viewers without making model capture
        # depend on the browser cache. Never serve a cached frame after failure.
        with self.frame_locks[name]:
            cached = self.frame_cache.get(name)
            if cached and cached[0] == url and time.monotonic() - cached[1] < .25:
                return cached[2]
            self.frame_cache.pop(name, None)
            frame = self.camera_source.fetch(name, url)
            self.frame_cache[name] = (url, time.monotonic(), frame)
            return frame

    async def maintenance(self):
        while True:
            await asyncio.to_thread(self.refresh_monitor)
            for visitor in list(self.visitors.values()):
                with suppress(Exception):
                    await asyncio.to_thread(self.remember_runner, visitor)
                    await asyncio.to_thread(self.remember_assessment_owner, visitor)
            now = time.monotonic()
            expired = [key for key, item in self.visitors.items()
                       if now - item.touched > self.idle_seconds or now - item.born > self.lifetime_seconds]
            for key in expired:
                visitor = self.visitors.pop(key)
                self.retire(visitor)
            await asyncio.sleep(1)

    def retire(self, visitor):
        visitor.retired = True
        visitor.saved_keys.clear()
        visitor.controller.forget_key()
        task = asyncio.create_task(asyncio.to_thread(visitor.close))
        self.cleanups.add(task)
        task.add_done_callback(self.cleanups.discard)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    self.task = asyncio.create_task(self.maintenance())
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    if self.task:
                        self.task.cancel()
                        with suppress(asyncio.CancelledError):
                            await self.task
                    visitors = list(self.visitors.values())
                    self.visitors.clear()
                    await asyncio.gather(*(asyncio.to_thread(v.close) for v in visitors))
                    if self.cleanups:
                        await asyncio.gather(*self.cleanups)
                    if not self.retain_recordings and not any(v.controller.busy() for v in visitors):
                        shutil.rmtree(self.root, ignore_errors=True)
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        try:
            await self.http(scope, receive, send)
        except RequestError as exc:
            await self.json(send, exc.status, {"error": exc.message,
                **({'subscription_setup': exc.setup} if exc.setup is not None else {})})
        except (ConnectionError, asyncio.CancelledError):
            raise
        except Exception:
            # No raw exceptions: upstream errors can contain URLs or credentials.
            await self.json(send, 503, {"error": "The request could not be completed. Please try again."})

    async def body(self, receive, *, max_bytes=24000):
        async def read():
            value = bytearray()
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    raise ConnectionError("Browser disconnected")
                value.extend(event.get("body", b""))
                if len(value) > max_bytes:
                    raise RequestError(413, "Request is too large")
                if not event.get("more_body"):
                    break
            try:
                payload = json.loads(value or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError()
                return payload
            except (ValueError, UnicodeError):
                raise RequestError(400, "Expected a JSON object") from None
        try:
            return await asyncio.wait_for(read(), 10)
        except asyncio.TimeoutError:
            raise RequestError(408, "Request timed out") from None

    async def http(self, scope, receive, send):
        path, method = scope["path"], scope["method"]
        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        if path == "/health" and method == "GET":
            await self.json(send, 200, {"ok": True})
            return
        if headers.get("host") != self.authority:
            raise RequestError(421, "Unrecognized website host")
        if await self.public_extension(scope, receive, send, headers):
            return
        if headers.get("sec-fetch-site") == "cross-site" and not (path == "/" and method == "GET"):
            raise RequestError(403, "Open the runner directly to continue")
        if method == "GET" and path == "/api/robots":
            await self.json(send, 200, {"selected": self.robot_id, "robots": [
                {**{k: robot[k] for k in ("id", "name", "url")}, "hardware": robot.get("hardware", ""), "connected": self.robot_connected(robot["id"])} for robot in self.robots]})
            return
        if method == "GET" and path == "/static/manrope-variable.ttf":
            await self.respond(send, 200, (ROOT / "static/manrope-variable.ttf").read_bytes(), "font/ttf")
            return
        if method == 'GET' and path == '/api/task-suggestions':
            from remote_yam.task_suggestions import read_suggestions
            try:
                suggestions = await asyncio.to_thread(read_suggestions, self.robot_id)
            except (OSError, ValueError, sqlite3.Error):
                raise RequestError(503, 'Task suggestions are unavailable. You can still write your own task.') from None
            await self.json(send, 200, {'robot_id': self.robot_id, 'suggestions': suggestions})
            return
        if method == "GET" and path in {"/", "/static/meeting.js", "/static/meeting.css", "/static/hosted.js", "/static/run-assessments.js", "/static/run-labels.js", "/static/run-data-chat.js", "/static/run-data-chat.css", "/static/task-cloud.js", "/static/replay-history.js", "/static/replay-progress.js", "/static/replay-email.js", "/static/reactions.js", "/static/model-picker.js", "/static/system-prompt.js", "/static/hosted.css", "/static/stream-health.js", "/static/live-viewers.js", "/static/hls.light.min.js", "/static/hls.min.js", "/static/robot-audio.js", "/static/robot-audio.css", "/static/observer-enhancement-worker.js"}:
            asset = ROOT / "static" / ("hosted.html" if path == "/" else path.rsplit("/", 1)[1])
            kind = "image/png" if path.endswith(".png") else "text/html" if path == "/" else "text/javascript" if path.endswith(".js") else "text/css"
            await self.respond(send, 200, (self.page() if path == "/" else asset.read_bytes()), kind if kind == "image/png" else kind + "; charset=utf-8")
            return
        if method == 'GET' and path == '/api/run-labels':
            # Public, read-only model predictions and imported human reviews.
            # Never write these into runner-owned assessments or revision votes.
            labels = ROOT / 'annotations' / 'run-labels.json'
            await self.json(send, 200, json.loads(labels.read_text()) if labels.exists() else {'version': 1, 'runs': []})
            return
        if method == 'GET' and path == '/api/run-catalog':
            from remote_yam.run_assessments import RunAssessments, score_models
            from remote_yam.run_search import rank_runs, MAX_QUERY_LENGTH
            from remote_yam.task_cloud import task_key
            try:
                query = parse_qs(scope.get('query_string', b'').decode())
                offset = int(query.get('offset', ['0'])[0])
                search = query.get('q', [''])[0].strip()
                models = query.get('model', [])
                view = query.get('view', ['table'])[0]
                if not 0 <= offset <= 1000000 or len(search) > MAX_QUERY_LENGTH or view not in {'table', 'cloud'}:
                    raise ValueError('Invalid catalog query')
                if len(models) > 100 or any(len(m) > 128 or any(ord(c) < 32 for c in m) for m in models):
                    raise ValueError('Invalid model filter')
            except (ValueError, UnicodeError) as exc:
                raise RequestError(400, str(exc) or 'Invalid catalog query') from None
            try:
                # Index all known tasks together, regardless of request filters.
                catalog = await asyncio.to_thread(self.past_runs.page, metadata=True)
                overlay = await asyncio.to_thread(self.run_assessments.summaries)
                all_rows = catalog['runs']
                rows = [dict(r, assessment=overlay.get(r['episode_id'], RunAssessments.summary()))
                        for r in all_rows if (not query.get('robot_id') or r['robot_id'] == query['robot_id'][0])]
                choices = sorted({r.get('model') or '__unrecorded__' for r in rows}, key=str.casefold)
                if models:
                    rows = [r for r in rows if (r.get('model') or '__unrecorded__') in models]
                score_groups = rows + [{'model': model} for model in models
                    if not any((r.get('model') or '__unrecorded__') == model for r in rows)]
                if search:
                    rows = rank_runs(rows, search)
                scores = score_models(rows, groups=score_groups)
                cloud = None
                if view == 'cloud':
                    await asyncio.to_thread(self.task_cloud.schedule, all_rows)
                    cloud = await asyncio.to_thread(self.task_cloud.snapshot, all_rows)
                    coordinates = cloud.pop('coordinates')
                    speeds = await asyncio.to_thread(self.run_names.replay_speeds)
                    for r in rows:
                        r['task_id'] = task_key(r['prompt'])
                        r['xyz'] = coordinates.get(r['task_id'])
                        if r['episode_id'] in speeds:
                            r['replay_speed'] = speeds[r['episode_id']]
                limit = 10000 if view == 'cloud' else 12
                selected = rows[:limit] if view == 'cloud' else rows[offset:offset+limit]
                if view == 'table':
                    selected = await asyncio.to_thread(self.past_runs.details_for, selected)
                    names = await asyncio.to_thread(self.run_names.names)
                    outcomes = await asyncio.to_thread(self.run_names.results)
                    speeds = await asyncio.to_thread(self.run_names.replay_speeds)
                    from remote_yam.past_runs import merge_run_result
                    for row in selected:
                        row['runner_name'] = names.get(row['episode_id'], 'Name not recorded')
                        if row['episode_id'] in speeds:
                            row['replay_speed'] = speeds[row['episode_id']]
                        merge_run_result(row, outcomes.get(row['episode_id'], {}))
                result = {'runs': selected, 'models': choices, 'scores': scores, 'total': len(rows),
                          'next_offset': offset+len(selected) if view == 'table' and offset+len(selected) < len(rows) else None,
                          'stale': catalog.get('stale', False), 'cloud': cloud,
                          'source': getattr(self.past_runs, 'source', 'public'),
                          'display_limit': limit, 'sampled': view == 'cloud' and len(rows) > limit}
            except Exception:
                raise RequestError(503, 'Run catalog is unavailable. Select Refresh to retry.') from None
            await self.json(send, 200, result)
            return
        if method == 'GET' and path == '/api/run-comparisons':
            runs = await asyncio.to_thread(self.run_names.comparisons, self.robot_id)
            await self.json(send, 200, {'runs': runs})
            return
        if method == 'GET' and path == '/api/past-runs':
            try:
                query = parse_qs(scope.get('query_string', b'').decode())
                episode_id = query.get('episode_id', [None])[0]
                if episode_id is not None and not re.fullmatch(r'ep_[A-Za-z0-9_-]+', episode_id):
                    raise ValueError()
                offset = int(query.get('offset', ['0'])[0])
                if not 0 <= offset <= 100000:
                    raise ValueError()
            except (ValueError, UnicodeError):
                raise RequestError(400, 'Invalid page') from None
            search = query.get('q', [''])[0].strip()
            from remote_yam.run_search import MAX_QUERY_LENGTH
            if len(search) > MAX_QUERY_LENGTH:
                raise RequestError(400, f'Search must be {MAX_QUERY_LENGTH} characters or fewer')
            model = query.get('model', [''])[0].strip()
            if len(model) > 128 or any(ord(c) < 32 for c in model):
                raise RequestError(400, 'Invalid model filter')
            try:
                if episode_id is not None:
                    row = await asyncio.to_thread(self.past_runs.get, episode_id)
                    if row is None:
                        row = await asyncio.to_thread(self.run_names.pending, episode_id, self.robot_id)
                    result = {'runs': [row] if row else [], 'next_offset': None, 'stale': False}
                else:
                    filters = {'query': search} if search else {}
                    if query.get('robot_id'):
                        filters['robot_id'] = query['robot_id'][0]
                    if model:
                        filters['model'] = model
                    result = await asyncio.to_thread(self.past_runs.page, offset, **filters)
                names = await asyncio.to_thread(self.run_names.names)
                outcomes = await asyncio.to_thread(self.run_names.results)
                replay_speeds = await asyncio.to_thread(self.run_names.replay_speeds)
                assessments = await asyncio.to_thread(self.run_assessments.summaries)
                for row in result['runs']:
                    row['assessment'] = assessments.get(row['episode_id'], self.run_assessments.summary())
                    row['runner_name'] = names.get(row['episode_id'], 'Name not recorded')
                    if row['episode_id'] in replay_speeds:
                        row['replay_speed'] = replay_speeds[row['episode_id']]
                    from remote_yam.past_runs import merge_run_result
                    merge_run_result(row, outcomes.get(row['episode_id'], {}))
            except Exception:
                raise RequestError(503, 'Past runs are temporarily unavailable. Please retry.') from None
            await self.json(send, 200, result)
            return
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get("cookie", ""))
        except CookieError:
            pass
        token = cookie.get(self.cookie_name)
        capability = token.value if token else ""
        visitor = self.visitors.get(capability)
        if visitor and (time.monotonic() - visitor.born > self.lifetime_seconds
                        or time.monotonic() - visitor.touched > self.idle_seconds):
            self.visitors.pop(capability)
            self.retire(visitor)
            visitor = None
        if method == "POST":
            if headers.get("origin") != self.origin:
                raise RequestError(403, "Request must come from this website")
            if headers.get("content-type", "").split(";", 1)[0] != "application/json":
                raise RequestError(415, "Use application/json")
        if method == "POST" and path == "/api/session":
            await self.body(receive)
            if visitor is None:
                capability, visitor = self.new_visitor()
            visitor.touched = time.monotonic()
            cookie_value = f"{self.cookie_name}={capability}; Path=/; HttpOnly; SameSite=Strict"
            if self.secure:
                cookie_value += "; Secure"
            application_setup, application_headers = await self.session_extension(cookie, visitor)
            local_setup = {}
            if self.local_codex:
                from remote_yam.subscription_setup import subscription_status
                local_setup = {'local_runner': True, 'default_provider': self.default_provider,
                               'codex': await asyncio.to_thread(subscription_status, 'codex')}
            if self.local_claude:
                from remote_yam.claude_policy import DEFAULT_MODEL as CLAUDE_MODEL
                from remote_yam.subscription_setup import subscription_status
                local_setup = {**local_setup, 'local_runner': True, 'default_provider': self.default_provider,
                               'claude': await asyncio.to_thread(subscription_status, 'claude'), 'claude_model': CLAUDE_MODEL}
            from remote_yam.system_prompts import catalog as system_prompt_catalog
            await self.json(send, 200, {**local_setup, **application_setup,
                                      "data_chat": {"available": self.data_chat is not None, "model": self.data_chat.model if self.data_chat else None},
                                      "system_prompts": system_prompt_catalog(self.joint_counts == (6,6)), "robot_id": self.robot_id, "video_stream": self.video_stream, "cameras": list(self.camera_names), "model_cameras": list(self.model_camera_names()), "joint_policy": self.joint_counts != (6,6), "claude_supported": self.hardware == "makerarm" or self.joint_counts in {(6,6), (5,5), (5,0)}, "csrf": visitor.csrf, "astra_enabled": bool(self.astra_endpoint), "groot_enabled": bool(self.groot_key_file), "groot_model": self.groot_model, "groot_label": self.groot_label, "runpod_providers": self.runpod_providers, "custom_endpoint_enabled": True,
                                      "custom_endpoint_profile": dict(robot_id=self.robot_id, joint_counts=list(self.joint_counts), cameras=list(self.model_camera_names()), action_dim=sum(count + 1 for count in self.joint_counts if count)),
                                      "simulation": self.simulation, "share_conversation": self.share_conversation,
                                      "dream_providers": self.dream_providers if self.dream_worker_ready() else {},
                                      **await self.chat_setup(visitor),
                                      "api_depth": {"available": bool(self.api_depth_provider_factory and self.local_codex),
                                                    "enabled": self.use_api_depth},
                                      "expires_in": int(self.lifetime_seconds - (time.monotonic() - visitor.born))},
                            [(b"set-cookie", cookie_value.encode())] + application_headers)
            return
        if visitor is None or visitor.retired:
            raise RequestError(401, "Your browser session ended. Reload to start a new one.")
        visitor.touched = time.monotonic()
        if method == "POST":
            if not secrets.compare_digest(headers.get("x-yam-runner-token", ""), visitor.csrf):
                raise RequestError(403, "Invalid browser session token")
            payload = await self.body(receive, max_bytes=600000 if path == '/api/run-data-chat' else 24000)
            if await self.action_extension(path, visitor, payload, cookie, send):
                return
            if path == '/api/run-data-chat':
                from remote_yam.run_data_chat import validate_payload, build_context, DataChatUnavailable
                try:
                    question, data_scope, history = validate_payload(payload)
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
                if self.data_chat is None:
                    raise RequestError(503, 'Data chat is not configured on this server. The run library and replays remain available.')
                if visitor.data_chat_busy or time.monotonic() - visitor.last_data_chat < 3:
                    raise RequestError(429, 'Please wait for the current answer before asking again.')
                visitor.data_chat_busy = True
                visitor.last_data_chat = time.monotonic()
                try:
                    catalog = await asyncio.to_thread(self.past_runs.page, metadata=True)
                    overlay = await asyncio.to_thread(self.run_assessments.summaries)
                    label_path = ROOT / 'annotations' / 'run-labels.json'
                    annotations = json.loads(label_path.read_text()) if label_path.exists() else {'runs': []}
                    context = await asyncio.to_thread(build_context, catalog, overlay, annotations,
                        data_scope, self.robot_id, question, history)
                    if not context['counts']['total']:
                        result = {'answer': 'No runs match this scope. Clear a filter or select a different box to discuss the data.',
                            'citations': [], 'requested_model': self.data_chat.model, 'resolved_model': None}
                    else:
                        result = await asyncio.to_thread(self.data_chat.answer, context, question, history)
                    result['scope'] = {k:v for k,v in context.items() if k not in ('evidence','by_model','repeated_tasks')}
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
                except DataChatUnavailable as exc:
                    raise RequestError(503, str(exc)) from None
                except Exception:
                    raise RequestError(503, 'Run data is unavailable. Refresh the library and try again.') from None
                finally:
                    visitor.data_chat_busy = False
            elif path == '/api/run-assessment':
                from remote_yam.run_assessments import AssessmentConflict
                eid, operation = payload.get('episode_id'), payload.get('operation', 'read')
                if not isinstance(eid, str) or not re.fullmatch(r'ep_[A-Za-z0-9_-]{1,100}', eid):
                    raise RequestError(400, 'Invalid episode ID')
                try:
                    await asyncio.to_thread(self.remember_runner, visitor)
                    await asyncio.to_thread(self.remember_assessment_owner, visitor)
                    if operation == 'assess':
                        await asyncio.to_thread(self.run_assessments.assess, eid, payload.get('label'),
                            payload.get('revision'), visitor.assessment_session, self.assessment_user(visitor))
                    elif operation == 'vote':
                        await asyncio.to_thread(self.run_assessments.vote, eid, payload.get('revision'),
                            payload.get('vote'), visitor.assessment_session)
                    elif operation != 'read':
                        raise ValueError('Unknown assessment operation')
                    result = await asyncio.to_thread(self.run_assessments.detail, eid,
                        visitor.assessment_session, self.assessment_user(visitor))
                except PermissionError as exc:
                    raise RequestError(403, str(exc)) from None
                except AssessmentConflict as exc:
                    raise RequestError(409, str(exc)) from None
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
            elif path == "/api/my-runs":
                try:
                    if 'email' in payload or 'episode_ids' in payload:
                        raise ValueError('Run history is limited to your current session')
                    offset = payload.get('offset', 0)
                    if type(offset) is not int or not 0 <= offset <= 100000:
                        raise ValueError('Invalid history page')
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
                try:
                    await asyncio.to_thread(self.remember_runner, visitor)
                    ids = visitor.episode_ids.copy()
                    result = await asyncio.to_thread(self.past_runs.page, offset, episode_ids=ids, robot_id=self.robot_id)
                    names = await asyncio.to_thread(self.run_names.names)
                    outcomes = await asyncio.to_thread(self.run_names.results)
                    replay_speeds = await asyncio.to_thread(self.run_names.replay_speeds)
                    assessments = await asyncio.to_thread(self.run_assessments.summaries)
                    from remote_yam.past_runs import merge_run_result
                    for row in result['runs']:
                        row['assessment'] = assessments.get(row['episode_id'], self.run_assessments.summary())
                        row['runner_name'] = names.get(row['episode_id'], 'Name not recorded')
                        if row['episode_id'] in replay_speeds:
                            row['replay_speed'] = replay_speeds[row['episode_id']]
                        merge_run_result(row, outcomes.get(row['episode_id'], {}))
                except Exception:
                    raise RequestError(503, 'Run history is temporarily unavailable. Please retry.') from None
            elif path == "/api/stream-health":
                from remote_yam.stream_health import public_report, log_report
                try:
                    report = public_report(payload)
                except ValueError:
                    raise RequestError(400, 'Invalid stream health report') from None
                if time.monotonic() - visitor.last_stream_report >= 1:
                    log_report(report)
                    visitor.last_stream_report = time.monotonic()
                result = {'ok': True}
            elif path == "/api/reactions":
                emoji = payload.get('emoji')
                if not isinstance(emoji, str) or emoji not in EMOJIS:
                    raise RequestError(400, 'Choose one of the available reactions')
                now = time.monotonic()
                if now - visitor.last_reaction < 1:
                    raise RequestError(429, 'Please wait a moment before reacting again')
                visitor.last_reaction = now
                result = {'reaction': await self.publish_reaction(visitor, emoji)}
            elif path == "/api/chat":
                name, text = payload.get("name", ""), payload.get("text", "")
                if not isinstance(name, str) or not isinstance(text, str):
                    raise RequestError(400, "Enter a name and message")
                name, text = name.strip(), text.strip()
                if not 1 <= len(name) <= 32 or not 1 <= len(text) <= 1000:
                    raise RequestError(400, "Use a name up to 32 characters and a message up to 1,000 characters")
                if time.monotonic() - visitor.last_chat < 2:
                    raise RequestError(429, "Please wait a moment before sending another message")
                visitor.last_chat = time.monotonic()
                await self.append_chat(visitor, name, text)
                result = {"ok": True}
            elif path == "/api/run":
                result = await asyncio.to_thread(self.launch, visitor, payload)
            elif path == '/api/runs/reset':
                result = await asyncio.to_thread(self.reset_runs, visitor)
            elif path == '/api/steer':
                result = await asyncio.to_thread(self.steer, visitor, payload)
            elif path == '/api/models':
                name = payload.get('provider')
                allowed = {'openai', 'anthropic'} | ({'codex'} if self.local_codex else set()) | ({'claude'} if self.local_claude else set())
                if not isinstance(name, str) or name not in allowed:
                    raise RequestError(400, 'Choose a configured model provider')
                key = payload.get('api_key', '') or visitor.saved_keys.get(name, '')
                if not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                    raise RequestError(400, 'Invalid provider API key')
                from remote_yam.model_catalog import discover_models
                result = await asyncio.to_thread(discover_models, name, key if name in ('openai', 'anthropic') else '')
            elif path == '/api/codex/check' and self.local_codex:
                from remote_yam.subscription_setup import verify_subscription
                from remote_yam.model_catalog import selected_model
                try:
                    model = selected_model('codex', payload.get('model', ''))
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
                result = await asyncio.to_thread(verify_subscription, 'codex', model)
            elif path == '/api/claude/check' and self.local_claude:
                from remote_yam.subscription_setup import verify_subscription
                from remote_yam.model_catalog import selected_model
                try:
                    model = selected_model('claude', payload.get('model', ''))
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
                result = await asyncio.to_thread(verify_subscription, 'claude', model)
            elif path in {"/api/stop", "/api/credentials/clear", "/api/disconnect", "/api/operator"}:
                result = await asyncio.to_thread(self.control, visitor, path)
                if path == "/api/disconnect":
                    self.visitors.pop(capability, None)
                    self.retire(visitor)
            else:
                raise RequestError(404, "Unknown action")
            await self.json(send, 200, result)
            return
        if method != "GET":
            raise RequestError(405, "Method not allowed")
        if path == "/api/chat":
            await self.json(send, 200, await self.chat_snapshot(visitor))
        elif path == "/api/status":
            now = time.monotonic()
            if headers.get('x-yam-watching') == '1':
                visitor.last_watched = now
            controller = visitor.controller
            if self.observation is not None:
                controller.update_monitor_observation(self.observation)
            if self.queue is not None:
                controller.update_queue_snapshot(self.queue)
            state = controller.status()
            # A browser's existing session deduplicates its tabs. Hidden tabs
            # must not clear a heartbeat sent by another visible tab.
            state['live_viewer_count'] = sum(
                not item.retired and now - item.last_watched < LIVE_VIEWER_SECONDS
                for item in self.visitors.values())
            # Only the owner receives local setup instructions after a login expires
            # during a run. No subprocess or live request is made by status polling.
            state['subscription_setup'] = None
            provider_name = (state.get('provider') or {}).get('provider')
            if state.get('error') and provider_name in {'codex', 'claude'}:
                from remote_yam.subscription_setup import subscription_failure
                failure = subscription_failure(provider_name, state['error'], setup={
                    'provider': provider_name, 'label': 'Opus (Claude)' if provider_name == 'claude' else 'Astra'})
                if failure['state'] == 'login_required':
                    failure['setup_prompt'] = visitor.subscription_prompts.get(provider_name, '')
                    failure['run_started'] = True
                    state['subscription_setup'] = failure
            if self.queue is None:
                state["queue_snapshot"] = None
            from remote_yam.operator_status import fresh_auto_queue
            state['robot_auto_queue_enabled'] = fresh_auto_queue(self.operator_auto_queue)
            # Station faults can happen before any visitor is assigned a run.
            from remote_yam.past_runs import public_robot_error
            observation = self.observation or {}
            observation = observation.get('observation') or observation.get('payload') or observation
            state['robot_fault'] = public_robot_error({
                'error': (observation.get('safety') or {}).get('reason')
            }) if observation.get('mode') == 'FAULT' else None
            state['runner_name'] = visitor.runner_name
            state['whats_running'] = []
            candidates = []
            for other in list(self.visitors.values()):
                current = other.controller.status()
                running = current.get('status') in {'preparing', 'running'}
                if running:
                    state['whats_running'].append({'runner_name': other.runner_name,
                        'task': other.runner_task, 'status': current['status']})
                if (other.runner_session_id or (other.runner_task and
                        ((current.get('provider') or {}).get('task_progress') or (current.get('provider') or {}).get('managed_execution')))) and current.get('status') != 'queued':
                    candidates.append((running, other.last_launch, other, current))
            state['public_run'] = None
            if candidates:
                _, _, owner, current = max(candidates, key=lambda item: item[:2])
                from remote_yam.public_conversation import project_events
                from remote_yam.run_errors import public_run_error
                from remote_yam.past_runs import public_robot_error
                events = project_events((current.get('interactions') or {}).get('events', []),
                                        (current.get('interactions') or {}).get('run_id'))
                state['public_run'] = {'run_id': (current.get('interactions') or {}).get('run_id'),
                    'attempt_id': current.get('attempt_id'),
                    'runner_name': owner.runner_name, 'task': owner.runner_task,
                    'launch_requested_at': owner.launch_requested_at,
                    'status': current['status'], 'events': events, 'error': public_run_error(current),
                    'step_timings': current.get('step_timings', []),
                    'run_metrics': current.get('run_metrics'),
                    'episode_id': current.get('episode_id'),
                    'model_name': model_display_name(current.get('provider')),
                    **({'task_progress':current['provider']['task_progress']} if (current.get('provider') or {}).get('task_progress') else {}),
                    **{k: current.get(k) for k in ('run_duration_s', 'run_started_at', 'run_ended_at', 'run_elapsed_s')}}
            shared_run = (state.get('queue_snapshot') or {}).get('public_run')
            same_run = (shared_run and state['public_run'] and shared_run.get('run_id')
                        and shared_run['run_id'] == state['public_run'].get('episode_id'))
            newer_shared_run = (shared_run and state['public_run']
                                and (shared_run.get('run_started_at') or 0) > (state['public_run'].get('run_started_at')
                                    or state['public_run'].get('launch_requested_at') or 0))
            local_preparation = (state['public_run'] and state['public_run'].get('status') == 'preparing'
                                 and not state['public_run'].get('episode_id'))
            if shared_run and not same_run and (shared_run.get('status') in {'preparing', 'running'} and not local_preparation
                                               or not state['public_run'] or newer_shared_run):
                local_run = state['public_run']
                # One station runs one policy: while this runner's run is live, the
                # station's copy is that run, which only this runner knows the model of.
                if (local_run and local_run.get('status') in {'preparing', 'running'}
                        and not shared_run.get('model_name')):
                    shared_run = {**shared_run, 'model_name': local_run['model_name']}
                state['public_run'] = shared_run
            names = {v.runner_session_id: v.runner_name for v in list(self.visitors.values()) if v.runner_session_id}
            for entry in (state.get('queue_snapshot') or {}).get('entries', []):
                entry['runner_name'] = names.get(entry.get('session_id'), 'Anonymous')
            # Camera URLs, filesystem paths, and transport details aren't UI data.
            observation = state.get("last_observation")
            if isinstance(observation, dict):
                observation = dict(observation)
                observation["images"] = {name: {"url": f"/api/monitor/cameras/{name}"} for name in self.camera_names}
                state["last_observation"] = observation
            if isinstance(state.get("provider"), dict):
                state["provider"].pop("recording_path", None)
                state["provider"].pop("endpoint", None)
                state["provider"]["api_key_configured"] = bool(getattr(controller._provider, "_api_key", ""))
            if isinstance(state.get("interactions"), dict):
                state["interactions"].pop("path", None)
            state.pop("lease_id", None)
            state["saved_key_providers"] = sorted(visitor.saved_keys)
            state["key_configured"] = bool(visitor.saved_keys)
            await self.json(send, 200, state)
        elif path.startswith("/api/monitor/cameras/"):
            name = path.rsplit("/", 1)[1]
            if name not in self.camera_names or not self.observation:
                raise RequestError(503, "NO SIGNAL")
            images = self.observation.get("images", {})
            spec = images.get(name, {})
            url = spec.get("url") if isinstance(spec, dict) else None
            if not url:
                raise RequestError(503, "NO SIGNAL")
            try:
                frame = await asyncio.to_thread(self.camera_frame, name, url)
            except Exception:
                raise RequestError(503, "NO SIGNAL") from None
            await self.respond(send, 200, frame.jpeg, "image/jpeg")
        elif path.startswith('/api/public-images/'):
            from remote_yam.interactions import recording_directory
            parts = path.split('/')
            if len(parts) != 5 or not re.fullmatch('[a-f0-9]{64}', parts[4]):
                raise RequestError(404, 'Image unavailable')
            run_id, digest = parts[3:]
            for owner in list(self.visitors.values()):
                snapshot = owner.controller.status().get('interactions') or {}
                if snapshot.get('run_id') != run_id:
                    continue
                permitted = any(image.get('digest') == digest
                    for event in snapshot.get('events', []) if event.get('kind') == 'model_request'
                    for image in (event.get('details') or {}).get('images', []))
                if not permitted:
                    continue
                directory = recording_directory(owner.directory, run_id)
                blob = directory / 'blobs' / digest
                if blob.is_symlink() or not blob.is_file() or blob.resolve().parent != (directory / 'blobs').resolve():
                    break
                await self.respond(send, 200, await asyncio.to_thread(blob.read_bytes), 'image/jpeg')
                return
            raise RequestError(404, 'Image unavailable')
        elif path == "/api/recordings":
            await self.json(send, 200, {"runs": await asyncio.to_thread(list_recordings, visitor.directory)})
        elif path.startswith("/api/recordings/"):
            parts = path.split("/")
            if len(parts) != 5:
                raise RequestError(404, "Recording unavailable")
            run_id, action = parts[3:]
            try:
                if action in {"interactions", "artifacts"}:
                    reader = read_recording if action == "interactions" else run_artifacts
                    result = await asyncio.to_thread(reader, visitor.directory, run_id)
                    result.pop("path", None)
                    await self.json(send, 200, result)
                elif action == "log.zip":
                    archive = await asyncio.to_thread(log_archive, visitor.directory, run_id)
                    with archive:
                        size = archive.seek(0, 2)
                        archive.seek(0)
                        await self.start_response(send, 200, "application/zip", size,
                                                  [(b"content-disposition", b'attachment; filename="yam-run-log.zip"')])
                        while True:
                            chunk = await asyncio.to_thread(archive.read, 1024 * 1024)
                            await send({"type": "http.response.body", "body": chunk, "more_body": bool(chunk)})
                            if not chunk:
                                break
                else:
                    raise ValueError()
            except (ValueError, OSError):
                raise RequestError(404, "Recording unavailable") from None
        else:
            raise RequestError(404, "Not found")

    def launch(self, visitor, payload, *, paid=False, provider_transform=None):
        self.remember_runner(visitor)
        self.validate_launch(visitor, payload, paid)
        from remote_yam.system_prompts import selection, apply as apply_system_prompt
        try:
            selected_prompt = selection(payload)
        except ValueError as exc:
            raise RequestError(400, str(exc)) from None
        if selected_prompt is not None and (self.joint_counts != (6,6) or payload.get('use_api_depth', self.use_api_depth if payload.get('provider') == 'codex' else False)):
            raise RequestError(400, 'System prompt editing is available for Cartesian YAM model runs')
        with visitor.lock:
            if visitor.retired:
                raise RequestError(401, "Browser session ended")
            if visitor.controller.busy() or visitor.controller.status()["status"] in ACTIVE:
                raise RequestError(409, "A run is already active. Stop it before starting another.")
            if time.monotonic() - visitor.last_launch < 5:
                raise RequestError(429, "Please wait a few seconds before starting another run.")
            if visitor.launches >= 20:
                raise RequestError(429, 'This browser session reached its 20-run limit. Click Reset runs in the page footer to continue.')
            name, key, prompt, model = (payload.get(k, "") for k in ("provider", "api_key", "prompt", "model"))
            from remote_yam.controller_executor import selected_executor
            try:
                controller_provider = selected_executor(payload.get('executor'), provider=name,
                    model=model, robot_id=self.robot_id)
            except ValueError as exc:
                raise RequestError(400, str(exc)) from None
            fast_provider = name in ('openai', 'codex', 'anthropic', 'claude')
            response_speed = payload.get('response_speed', 'fast' if fast_provider else 'standard')
            if response_speed not in ('standard', 'fast'):
                raise RequestError(400, 'Choose standard or fast model speed')
            if response_speed == 'fast' and not fast_provider:
                raise RequestError(400, 'Fast mode is unavailable for this provider')
            effort = payload.get('reasoning_effort', 'low')
            if name == 'codex' and effort not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'):
                raise RequestError(400, 'Choose a supported model effort')
            if name == 'claude' and effort not in ('low', 'medium', 'high', 'xhigh', 'max'):
                raise RequestError(400, 'Choose a supported Claude model effort')
            if not paid and key == "" and isinstance(name, str):
                key = visitor.saved_keys.get(name, "")
            share_conversation = payload.get("share_conversation", True)
            if type(share_conversation) is not bool:
                raise RequestError(400, "Conversation sharing must be true or false")
            use_api_depth = payload.get("use_api_depth", self.use_api_depth if name == 'codex' else False)
            if type(use_api_depth) is not bool:
                raise RequestError(400, "API depth must be true or false")
            if use_api_depth and not (name == 'codex' and self.local_codex and self.api_depth_provider_factory):
                raise RequestError(400, "API depth requires a configured local Astra runner")
            maximum_duration = 1200 if name in ('dream', 'dream_flash') else 600
            default_duration = 120 if name in ('dream', 'dream_flash') else 300
            duration = payload.get("run_duration_s", default_duration)
            if type(duration) is not int or not 60 <= duration <= maximum_duration:
                raise RequestError(400, f"Choose a run duration from 1 to {maximum_duration // 60} minutes")
            runner_name = payload.get('runner_name', 'Anonymous')
            try:
                handles = social_handles(payload)
                from remote_yam.run_video_email import recipient
                recipient(payload)
            except ValueError as exc:
                raise RequestError(400, str(exc)) from None
            if not isinstance(runner_name, str) or not 1 <= len(runner_name.strip()) <= 32 or any(ord(c) < 32 for c in runner_name):
                raise RequestError(400, 'Enter a name of 1–32 characters')
            if name not in ({"local_raise_lower", "openai", "astra", "anthropic"} | ({"codex"} if self.local_codex else set())
                            | ({"claude"} if self.local_claude else set())) | ({"groot"} if self.groot_key_file else set()) | set(self.extra_providers) | {"custom_endpoint"} | ({'dream'} if controller_provider else set()):
                raise RequestError(400, "Choose a supported provider")
            if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
                raise RequestError(400, "Enter a task of up to 4,000 characters")
            if not isinstance(model, str) or len(model) > 128 or any(ord(c) < 32 for c in model):
                raise RequestError(400, "Invalid model name")
            if name in ('openai', 'codex', 'anthropic', 'claude'):
                from remote_yam.model_catalog import selected_model
                try:
                    model = selected_model(name, model)
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
            if controller_provider is None and name not in ({"local_raise_lower", "codex", "claude", "groot", "custom_endpoint"} | set(self.extra_providers)) and (not isinstance(key, str) or not 8 <= len(key) <= 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key)):
                raise RequestError(400, "Enter your provider API key")
            if name == 'custom_endpoint' and (not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in key)):
                raise RequestError(400, 'Enter a valid endpoint bearer key or leave it blank')
            if name != 'custom_endpoint' and payload.get("endpoint"):
                raise RequestError(400, "Provider endpoints are configured by the service")
            if name == "astra" and not self.astra_endpoint:
                raise RequestError(400, "Astra is not configured on this service")
            if name == "local_raise_lower":
                prompt = "Raise and lower both arms for three cycles."
            claude_supported = self.hardware == 'makerarm' or self.joint_counts in {(5,5), (5,0)}
            if self.joint_counts != (6,6) and name not in ({'openai', 'custom_endpoint'} | ({'codex'} if self.local_codex else set())
                    | ({'anthropic'} | ({'claude'} if self.local_claude else set()) if claude_supported else set())):
                raise RequestError(400, 'This robot requires an OpenAI or supported local Codex runner')
            if name in {'codex', 'claude'}:
                from remote_yam.subscription_setup import verify_subscription
                setup = verify_subscription(name, model)
                visitor.subscription_prompts[name] = setup['setup_prompt']
                if not setup['ready']:
                    raise RequestError(409, f"{setup['label']} needs setup on this computer. " + setup['message'], setup=setup)
            if controller_provider is not None:
                provider = controller_provider
            elif use_api_depth:
                provider = self.api_depth_provider_factory(name, key, model, visitor.directory)
            elif name == 'custom_endpoint':
                from remote_yam.custom_endpoint_policy import CustomEndpointAdapter
                try:
                    provider = CustomEndpointAdapter(key, endpoint=payload.get('endpoint'),
                        camera_source=self.camera_source, robot_id=self.robot_id,
                        joint_counts=self.joint_counts, camera_names=self.model_camera_names())
                except ValueError as exc:
                    raise RequestError(400, str(exc)) from None
            elif name in self.extra_providers:
                provider = self.extra_providers[name](model, visitor.directory)
            elif name == 'groot':
                from remote_yam.groot_policy import GrootAdapter
                if model not in ('', self.groot_model):
                    raise RequestError(400, 'Unknown GR00T checkpoint')
                settings = {key: self.groot_config[key] for key in
                            ('endpoint', 'norm_tag', 'artifact_sha256') if key in self.groot_config}
                provider = GrootAdapter(Path(self.groot_key_file).read_text().strip(),
                                        camera_source=self.camera_source, model=self.groot_model, **settings)
            elif self.hardware == 'makerarm' and not self.provider_factory:
                from remote_yam.makerarm_policy import MakerArmOpenAIAdapter, MakerArmCodexAdapter, MakerArmClaudeAdapter, MakerArmAnthropicAdapter
                mapping = ROOT / '.local' / 'robot-calibrations' / (hashlib.sha256(self.robot_id.encode()).hexdigest() + '.json')
                if not mapping.is_file():
                    raise RequestError(400, 'MakerArm Cartesian control requires a verified motor-to-URDF mapping on this runner')
                kwargs = dict(camera_source=self.camera_source, recording_root=visitor.directory,
                              calibration_path=mapping, camera_names=self.camera_names)
                try:
                    if name in {'claude', 'anthropic'}:
                        from remote_yam.claude_policy import DEFAULT_MODEL as CLAUDE_MODEL
                        provider = (MakerArmClaudeAdapter(model or CLAUDE_MODEL, **kwargs) if name == 'claude'
                                    else MakerArmAnthropicAdapter(key, model or CLAUDE_MODEL, **kwargs))
                    else:
                        provider = (MakerArmCodexAdapter(model or 'gpt-6-astra', **kwargs) if name == 'codex'
                                    else MakerArmOpenAIAdapter(key, model or 'gpt-6-astra', **kwargs))
                except (RuntimeError, ValueError, KeyError) as exc:
                    raise RequestError(400, str(exc)) from None
                provider._urlopen = request.build_opener(NoRedirect).open
            elif self.joint_counts == (5,5) and not self.provider_factory:
                from remote_yam.bimanual_so101_policy import BimanualSO101OpenAIAdapter, BimanualSO101CodexAdapter, BimanualSO101ClaudeAdapter, BimanualSO101AnthropicAdapter
                calibration_path = ROOT / '.local' / 'robot-calibrations' / (hashlib.sha256(self.robot_id.encode()).hexdigest() + '.json')
                from remote_yam.so101_trajectory import load_joint_profile
                calibration_path = calibration_path if calibration_path.is_file() else None
                joint_profile = None if calibration_path else load_joint_profile(self.robot_id)
                if calibration_path is None and joint_profile is None:
                    raise RequestError(400, 'No bimanual SO101 joint limits configured for this robot. Add robot-specific profiles or local calibrations.')
                kwargs = dict(camera_source=self.camera_source, recording_root=visitor.directory,
                              calibration_path=calibration_path, joint_profile=joint_profile, camera_names=self.policy_camera_names)
                try:
                    if name in {'claude', 'anthropic'}:
                        from remote_yam.claude_policy import DEFAULT_MODEL as CLAUDE_MODEL
                        provider = (BimanualSO101ClaudeAdapter(model or CLAUDE_MODEL, **kwargs) if name == 'claude'
                                    else BimanualSO101AnthropicAdapter(key, model or CLAUDE_MODEL, **kwargs))
                    else:
                        provider = (BimanualSO101CodexAdapter(model or 'gpt-6-astra', **kwargs) if name == 'codex'
                                    else BimanualSO101OpenAIAdapter(key, model or 'gpt-6-astra', **kwargs))
                except (RuntimeError, ValueError, OSError, KeyError) as exc:
                    raise RequestError(400, str(exc)) from None
                provider._urlopen = request.build_opener(NoRedirect).open
            elif self.joint_counts == (5,0) and not self.provider_factory:
                from remote_yam.so101_policy import SO101OpenAIAdapter, SO101CodexAdapter, SO101ClaudeAdapter, SO101AnthropicAdapter
                from remote_yam.so101_trajectory import load_joint_profile
                # An explicit local calibration overrides the bundled robot-specific limits.
                calibration_path = ROOT / '.local' / 'robot-calibrations' / (hashlib.sha256(self.robot_id.encode()).hexdigest() + '.json')
                calibration_path = calibration_path if calibration_path.is_file() else None
                joint_profile = None if calibration_path else load_joint_profile(self.robot_id)
                if calibration_path is None and joint_profile is None:
                    raise RequestError(400, 'No SO101 joint limits configured for this robot. Add a robot-specific joint profile or local LeRobot calibration.')
                kwargs = {"camera_source": self.camera_source, "recording_root": visitor.directory,
                          "calibration_path": calibration_path, "joint_profile": joint_profile}
                try:
                    if name in {'claude', 'anthropic'}:
                        from remote_yam.claude_policy import DEFAULT_MODEL as CLAUDE_MODEL
                        provider = (SO101ClaudeAdapter(model or CLAUDE_MODEL, **kwargs) if name == 'claude'
                                    else SO101AnthropicAdapter(key, model or CLAUDE_MODEL, **kwargs))
                    else:
                        provider = (SO101CodexAdapter(model or 'gpt-6-astra', **kwargs) if name == 'codex'
                                    else SO101OpenAIAdapter(key, model or 'gpt-6-astra', **kwargs))
                except RuntimeError as exc:
                    raise RequestError(400, str(exc)) from None
                provider._urlopen = request.build_opener(NoRedirect).open
            elif self.joint_counts != (6,6) and not self.provider_factory:
                from remote_yam.joint_policy import JointPolicy, CodexJointPolicy
                try:
                    provider = (CodexJointPolicy(model or 'gpt-6-astra', joint_counts=self.joint_counts, camera_source=self.camera_source) if name == 'codex' else
                        JointPolicy(key, model or 'gpt-6-astra', joint_counts=self.joint_counts, camera_source=self.camera_source))
                except RuntimeError as exc:
                    raise RequestError(400, str(exc)) from None
                provider._urlopen = request.build_opener(NoRedirect).open
            elif self.provider_factory:
                provider = self.provider_factory(name, key, model, visitor.directory)
            elif name == 'codex':
                from remote_yam.codex_policy import CodexAdapter
                try:
                    provider = CodexAdapter(model or 'gpt-6-astra', camera_source=self.camera_source,
                                            recording_root=visitor.directory)
                except RuntimeError as exc:
                    raise RequestError(400, str(exc)) from None
            elif name == 'claude':
                from remote_yam.claude_policy import ClaudeAdapter, DEFAULT_MODEL as CLAUDE_MODEL
                try:
                    provider = ClaudeAdapter(model or CLAUDE_MODEL, camera_source=self.camera_source,
                                             recording_root=visitor.directory)
                except (RuntimeError, ValueError) as exc:
                    raise RequestError(400, str(exc)) from None
            elif name == 'anthropic':
                from remote_yam.anthropic_policy import AnthropicAdapter, DEFAULT_MODEL
                provider = AnthropicAdapter(key, model or DEFAULT_MODEL, camera_source=self.camera_source,
                                            recording_root=visitor.directory)
                provider._urlopen = request.build_opener(NoRedirect).open
            elif name == "local_raise_lower":
                provider = RepeatingRaiseLowerAdapter(cycles=3)
            else:
                kwargs = {"camera_source": self.camera_source, "recording_root": visitor.directory}
                provider = (OpenAIAdapter(key, model or "gpt-6-astra", **kwargs) if name == "openai"
                            else AstraAdapter(key, model or "astra-default", self.astra_endpoint, **kwargs))
                provider._urlopen = request.build_opener(NoRedirect).open
            if name in {'codex', 'claude'}:
                provider.reasoning_effort = effort
            if fast_provider:
                provider.response_speed = response_speed
            try:
                apply_system_prompt(provider, selected_prompt)
            except ValueError as exc:
                close = getattr(provider, 'close_transport', None)
                if callable(close):
                    close()
                raise RequestError(400, str(exc)) from None
            if provider_transform is not None:
                provider = provider_transform(provider)
            visitor.last_launch = time.monotonic()
            visitor.launch_requested_at = time.time()
            visitor.launches += 1
            try:
                visitor.controller._share_conversation = (self.share_conversation and share_conversation
                    and getattr(provider, "share_conversation", True))
                # Record the effective model, including configured defaults/checkpoints.
                visitor.controller._session_api.setup(
                    {**payload, "model": provider.public_config().get("model") or model}, paid=paid)
                visitor.controller.join_and_run(provider, prompt.strip(), run_duration_s=duration)
                with visitor.controller._lock:
                    analytics_run = getattr(visitor.controller, "_analytics_run", None)
                    if analytics_run:
                        analytics_run["run_route"] = "paid" if paid else "direct"
                visitor.runner_task = prompt.strip()
                visitor.runner_name = runner_name.strip()
                visitor.runner_session_id = visitor.controller.status().get('session_id')
                visitor.controller._interactions.add('runner', 'Run submitted by ' + visitor.runner_name, runner_name=visitor.runner_name)
            except Exception:
                if hasattr(provider, "_api_key"):
                    provider._api_key = ""
                close = getattr(provider, 'close_transport', None)
                if callable(close):
                    with suppress(Exception):
                        close()
                visitor.controller.disconnect("launch_failed")
                raise RequestError(503, "Could not join the robot queue. Please try again.") from None
            # Optional metadata must never cancel an already accepted session.
            try:
                save_handles(self.social_database, visitor.runner_session_id, visitor.runner_name, handles)
            except Exception as exc:
                print('[contacts] save_failed error_type=' + type(exc).__name__, flush=True)
                visitor.controller._session_api.note(
                    'contact_save_failed', {'error_type': type(exc).__name__}, visitor.runner_session_id)
            if controller_provider is None and not paid and name not in ({"local_raise_lower", "codex", "claude", "groot", "custom_endpoint"} | set(self.extra_providers)):
                visitor.saved_keys[name] = key
            current = visitor.controller.status()
            return {"ok": True, "saved_key_providers": sorted(visitor.saved_keys),
                    "attempt_id": current.get('attempt_id'), "status": current['status']}

    def steer(self, visitor, payload):
        from remote_yam.steering import SteeringError
        with visitor.lock:
            if visitor.retired:
                raise RequestError(401, 'Browser session ended')
            try:
                # Authority comes exclusively from the authenticated visitor;
                # public run/session IDs never select a target controller.
                row = visitor.controller.steer(payload.get('attempt_id'),
                    payload.get('text'), payload.get('request_id'))
            except SteeringError as exc:
                raise RequestError(exc.status, str(exc)) from None
            return {'ok': True, 'message': row}

    def reset_runs(self, visitor, *, allowance_reset=None):
        # Serialize with launch/close; resetting an allowance must never stop a
        # controller, retire a visitor or remove their recordings/credentials.
        with visitor.lock:
            if visitor.retired:
                raise RequestError(401, 'Browser session ended')
            if visitor.controller.busy() or visitor.controller.status()['status'] in ACTIVE:
                raise RequestError(409, 'Wait for your run to finish, or use Stop, before resetting runs.')
            # Hosting products can renew their own allowance under the same
            # idle/launch lock. Failed renewal must not clear the shared cap.
            extra = allowance_reset() if allowance_reset is not None else {}
            visitor.launches = 0
            return {'ok': True, **extra}

    def control(self, visitor, path):
        self.remember_runner(visitor)
        with visitor.lock:
            if visitor.retired:
                raise RequestError(401, "Browser session ended")
            controller = visitor.controller
            # Forget means cancel future inference as well as clearing the key.
            controller.forget_key()
            if path in {"/api/credentials/clear", "/api/disconnect"}:
                visitor.saved_keys.clear()
            if path == "/api/operator":
                controller.call_operator()
            elif path == "/api/disconnect":
                controller.disconnect("browser_disconnect")
            else:
                controller.stop("user_requested" if path == "/api/stop" else "browser_stop_or_forget")
            return {"ok": True, "key_configured": bool(visitor.saved_keys), "saved_key_providers": sorted(visitor.saved_keys)}

    async def start_response(self, send, status, content_type, size, extra=()):
        headers = [(b"content-type", content_type.encode()), (b"content-length", str(size).encode()),
                   (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                   (b"referrer-policy", b"no-referrer"),
                   (b"content-security-policy", b"default-src 'none'; script-src 'self' https://www.googletagmanager.com; style-src 'self'; font-src 'self'; connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://www.googletagmanager.com; img-src 'self' https://*.google-analytics.com https://www.googletagmanager.com; media-src https://huggingface.co https://*.huggingface.co https://*.hf.co; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]
        if self.secure:
            headers.append((b"strict-transport-security", b"max-age=31536000"))
        await send({"type": "http.response.start", "status": status, "headers": headers + list(extra)})

    async def respond(self, send, status, body, content_type, extra=()):
        await self.start_response(send, status, content_type, len(body), extra)
        await send({"type": "http.response.body", "body": body})

    async def json(self, send, status, payload, extra=()):
        await self.respond(send, status, json.dumps(payload, allow_nan=False).encode(), "application/json", extra)
