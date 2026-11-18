"""Generated JSON -> real RunnerController -> serializer -> mock station.

The station exercises canonical lease/cursor events and packet validation,
never a physical endpoint. It cannot certify native predictive contacts.
"""
from copy import deepcopy
import io
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('GEMINI_TEST_RUNNER_ROOT', Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from remote_yam.controller import RunnerController
from remote_yam import session
from controller_bridge import GeneratedControllerProvider, BridgeProtocolError


FEEDBACK = dict(left_joints_deg=[math.degrees(q) for q in (.12345, 1.6, 1.2, -1.1, .01234, -.23456)],
                right_joints_deg=[math.degrees(q) for q in (-.23456, 1.4, 1.3, -1.2, -.12345, .34567)],
                left_gripper=.9992793312193716, right_gripper=.412345678)


def command(request_id, value, arm='left'):
    return dict(kind='command', request_id=request_id,
                payload=dict(commands={f'{arm}/follower/goal_position/gripper':value}, duration_s=.2))


class Channel:
    def __init__(self, inputs):
        self.inputs, self.sent, self.closed = list(inputs), [], False
        self.on_receive = lambda: None
    def receive(self, cancelled):
        self.on_receive()
        if not self.inputs: raise AssertionError('Test channel exhausted')
        return json.dumps(self.inputs.pop(0))
    def send(self, value): self.sent.append(deepcopy(value))
    def close(self): self.closed = True


class SerializerStation(session.MockSessionAPI):
    DEFAULT_OBSERVATIONS = (FEEDBACK,)
    def __init__(self):
        super().__init__()
        self.wire = []
        self.http = session.HttpSessionAPI('https://offline.invalid', supports_trajectories=True)
    def get_session(self, session_id):
        # The old mock omits these read fields used by the current controller's
        # refresh protocol. Expose its actual lease/cursor/active state, without
        # changing any command validation or accepting an arbitrary packet.
        result = super().get_session(session_id)
        record = self._record(session_id)
        result.update(lease_id=record['lease_id'], latest_observation_step=record['next_command_step'],
                      active_trajectory=record['active_trajectory'])
        return result
    def submit_trajectory(self, session_id, *args):
        self.http._session_capabilities[session_id] = 'synthetic-offline-capability'
        def transport(request, **kwargs):
            self.wire.append(json.loads(request.data))
            return io.BytesIO(b'{"offline_transport":true}')
        with patch.object(session.request, 'urlopen', transport):
            self.http.submit_trajectory(session_id, *args)
        return super().submit_trajectory(session_id, *args)


class ControllerBridgeTests(unittest.TestCase):
    def setup_runner(self, inputs):
        channel, api = Channel(inputs), SerializerStation()
        provider = GeneratedControllerProvider(ROOT, channel, controller_sha256='c'*64)
        controller = RunnerController(api, share_conversation=False)
        controller.update_monitor_observation(api.get_robot_observation('yam-1'))
        controller.join(provider, 'Offline controller bridge check')
        return channel, api, provider, controller

    def test_real_runner_local_rejection_new_request_and_measured_completion(self):
        channel, api, provider, controller = self.setup_runner([
            command(0, -1e-16), command(1, 0.), command(2, 1., 'right'), dict(kind='complete', request_id=3)])
        events = []; provider.interaction_sink = lambda *args, **kwargs: events.append((args, kwargs))
        controller._run_loop(None)
        self.assertIsNone(controller.status()['error'])
        self.assertTrue(provider.completed)
        self.assertEqual(len(api.wire), 2)
        self.assertEqual(len(api.trajectory_log), 2)
        first, second = [entry['waypoints'] for entry in api.wire]
        self.assertEqual(first[-1]['left_gripper'], 0.)
        self.assertEqual(second[-1]['right_gripper'], 1.)
        for p in first:
            self.assertEqual(p['right_gripper'], FEEDBACK['right_gripper'])
            for side in ('left','right'): self.assertEqual(p[side+'_joints_deg'], FEEDBACK[side+'_joints_deg'])
        self.assertEqual([p['step_id'] for p in first+second], [0,1,2,3])
        rejects = [v for v in channel.sent if v['kind']=='rejected']
        self.assertEqual(len(rejects), 1); self.assertFalse(rejects[0]['dispatched'])
        self.assertEqual(rejects[0]['stage'], 'local_validation')
        self.assertEqual([v['request_id'] for v in channel.sent if v['kind']=='completed'], [1,2])
        for value in channel.sent:
            text=json.dumps(value)
            self.assertNotIn('lease_', text); self.assertNotIn('capability', text)
        self.assertEqual(provider.public_config()['model'], 'Gemini Robotics')
        self.assertEqual(events[0][1]['stage'], 'local_validation')

    def test_stop_during_channel_read_discards_late_command_before_transport(self):
        channel, api, provider, controller = self.setup_runner([command(0, 0.)])
        channel.on_receive = lambda: controller.stop('user_requested')
        controller._run_loop(None)
        self.assertFalse(api.wire); self.assertFalse(api.trajectory_attempts)
        self.assertFalse(provider.completed)

    def test_stale_cursor_and_unknown_operations_never_dispatch(self):
        for message in (command(1, 0.), dict(kind='shell', request_id=0, command='true'),
                        dict(kind='command', request_id=True, payload={})):
            channel, api, provider, controller = self.setup_runner([message])
            controller._run_loop(None)
            self.assertFalse(api.wire); self.assertFalse(api.trajectory_attempts)
            self.assertIn('BridgeProtocolError', controller.status()['error'])

    def test_completion_and_failure_cannot_invent_or_replay_measured_success(self):
        channel, api, provider, controller = self.setup_runner([])
        with self.assertRaises(BridgeProtocolError): provider.trajectory_completed(dict(settled=True,step_id=2),2)
        provider.pending=dict(request_id=0,count=2,last_step=1)
        with self.assertRaises(BridgeProtocolError): provider.trajectory_completed(dict(settled=False,step_id=2),2)
        with self.assertRaisesRegex(BridgeProtocolError,'no automatic retry'):
            provider.trajectory_failed('joint_settle_timeout','unchanged native failure',2)
        self.assertIsNone(provider.pending); self.assertFalse(channel.sent); self.assertFalse(api.wire)
        controller.stop()


if __name__ == '__main__': unittest.main()
