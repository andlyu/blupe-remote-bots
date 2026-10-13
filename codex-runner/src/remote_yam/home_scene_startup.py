"""Optional Session API home-scene extension for RunnerController."""
import hashlib
import math
import time

from .feedback import feedback_decision
from .home_scene import HomePlan, decode_scene, eligible, profile_key


class HomeSceneStartup:
    def _home_event(self, state, **details):
        self._interactions.add('home_scene', 'Home scene: '+state, state=state, **details)

    def _cancel_home_plan(self, provider=None):
        job = getattr(self, '_home_plan', None)
        if job is not None and (provider is None or job.provider is provider):
            job.close(cancel=True)

    def _poll_home_scene(self):
        provider = self._provider
        api = getattr(self._session_api, 'home_scene', None)
        if (self._stop_event.is_set() or self._status not in {'queued','preparing'}
                or not eligible(provider) or not callable(api)
                or getattr(self._session_api, 'supports_trajectories', False) is not True
                or getattr(self, '_home_disabled', False) or self._home_plan is not None):
            return
        if time.monotonic() < getattr(self, '_home_next_poll', 0):
            return
        self._home_next_poll = time.monotonic()+.5
        try:
            if not self._home_registered:
                api(self._session_id, {'profile':profile_key(provider)})
                self._home_registered = True
                self._first_call_wander = False
            offer = api(self._session_id)
            scene = offer.get('scene')
            if not scene:
                return
            decode_scene(scene, self._robot_id)
            if self._stop_event.is_set() or self._provider is not provider:
                return
            self._home_plan = HomePlan(provider, self._prompt, scene, self._robot_id,
                self._session_id, lambda: self._provider_cancelled(provider))
            self._home_event('planning', scene_id=scene['scene_id'],
                             cache_age_s=time.time()-scene['captured_at'])
        except Exception as exc:
            # Old servers, malformed caches, and extension outages are ordinary
            # fresh-start cases; never turn these into a robot action or retry loop.
            self._home_disabled = True
            self._home_event('unavailable', reason=type(exc).__name__)

    def _fresh_home(self, session_id, episode_id, lease_id):
        if self._stop_event.is_set():
            raise RuntimeError('Home planning cancelled')
        live = self._session_api.get_session(session_id)
        if (live.get('status') != 'running' or live.get('episode_id') != episode_id
                or live.get('lease_id') != lease_id or live.get('latest_observation_step') != 0
                or live.get('active_trajectory') is not None):
            raise RuntimeError('Session changed before first motion')
        raw = self._session_api.get_robot_observation(self._robot_id)
        fresh = raw.get('observation') or raw.get('payload') or raw
        if fresh.get('jetson_id') != self._robot_id:
            raise RuntimeError('Robot changed before first motion')
        decision, reason = feedback_decision(fresh, fresh, now=time.time(), require_home=True)
        if decision != 'ready':
            raise RuntimeError('First motion blocked: '+reason)
        for arm in ('left','right'):
            grip = fresh.get(arm+'_gripper')
            if type(grip) not in (int,float) or not math.isfinite(grip) or abs(grip-1.) > .02:
                raise RuntimeError('First motion requires confirmed open grippers')
        if self._stop_event.is_set():
            raise RuntimeError('Home planning cancelled')
        return fresh

    def _take_home_plan(self, provider, observation):
        job = self._home_plan
        if job is None:
            return None
        wait_started = time.monotonic()
        while not job.done.wait(.05):
            if self._provider_cancelled(provider):
                job.close(cancel=True)
                return None
        job.close()
        self._home_event('plan_finished', robot_wait_for_plan_s=time.monotonic()-wait_started,
                         plan_wait_for_home_s=max(0.,wait_started-job.started-job.elapsed_s) if job.elapsed_s is not None else None,
                         first_executable_plan_s=job.elapsed_s)
        try:
            if self._provider_cancelled(provider) or job.session_id != self._session_id:
                raise ValueError('cancelled')
            if job.error is not None or not job.result:
                raise ValueError('inference_failed_or_no_executable_plan')
            decode_scene(job.scene, self._robot_id)
            identity = (self._session_id, self._episode_id, self._lease_id)
            fresh = self._fresh_home(*identity)
            receipt = self._session_api.home_scene(self._session_id)
            if (receipt.get('ready') is not True or receipt.get('scene_id') != job.scene['scene_id']
                    or receipt.get('config_sha256') != job.scene['config_sha256']
                    or receipt.get('boot_id') != job.scene['boot_id']
                    or receipt.get('lease_id') != self._lease_id
                    or receipt.get('episode_id') != self._episode_id):
                raise ValueError('startup_not_verified')
            self._record_first_plan(provider, job.elapsed_s, job.scene["config_sha256"])
            # Fresh source timestamps and exact JPEG equality deliberately fail
            # closed on camera noise, lighting, changed objects, or proxy transforms.
            frames = provider._camera_source.capture(fresh)
            if {f.name for f in frames} != set(job.scene['frames']):
                raise ValueError('camera_set_changed')
            stamps = []
            for frame in frames:
                stamp = frame.source_captured_at
                if (stamp is None or not 0 <= time.time()-stamp <= 2.
                        or stamp < observation['observed_at']-.15):
                    raise ValueError('unverifiable_fresh_frame')
                stamps.append(stamp)
                if hashlib.sha256(frame.jpeg).hexdigest() != job.scene['frames'][frame.name]['sha256']:
                    raise ValueError('scene_changed')
            if max(stamps)-min(stamps) > .15:
                raise ValueError('incoherent_validation_frames')
            after = self._fresh_home(*identity)
            if time.time()-min(stamps) > 2.:
                raise ValueError('scene_validation_expired')
            for arm in ('left','right'):
                if any(abs(a-b) > .25 for a,b in zip(after[arm+'_joints_deg'], job.scene['observation'][arm+'_joints_deg'])):
                    raise ValueError('home_pose_changed')
            if provider.steering.pending():
                raise ValueError('owner_steering_changed')
            job.bind(observation)
            self._home_accepted_scene = job.scene
            self._home_accepted_job = job
            self._home_validation_at = min(stamps)
            self._home_event('hit', scene_id=job.scene['scene_id'])
            return job.result
        except Exception as exc:
            job.discard()
            self._home_event('fallback', reason=str(exc)[:100])
            return None
        finally:
            self._home_plan = None

    def _record_first_plan(self, provider, elapsed_s, config_sha256=None):
        if not eligible(provider) or not self._home_registered or self._home_sample_recorded:
            return
        if type(elapsed_s) not in (int,float) or not math.isfinite(elapsed_s) or elapsed_s <= 0:
            return
        try:
            receipt = self._session_api.home_scene(self._session_id)
            config_sha256 = config_sha256 or receipt.get('config_sha256')
            if not config_sha256:
                return
            self._session_api.home_scene(self._session_id, {'profile':profile_key(provider),
                'first_executable_plan_s':elapsed_s, 'config_sha256':config_sha256})
            self._home_sample_recorded = True
            self._home_event('latency_sample', first_executable_plan_s=elapsed_s)
        except Exception:
            self._home_event('latency_sample_unavailable')
