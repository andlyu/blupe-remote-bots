"""Real controller completion -> RoboHarness -> canonical wire, without hardware."""
from copy import deepcopy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from remote_yam.controller import RunnerController
from remote_yam.session import HttpSessionAPI
from remote_yam.roboharness_contract import decision_response
from test_roboharness_contract import decision
from test_roboharness_policy import adapter

FIXTURE=json.loads((Path(__file__).parent/'fixtures/roboharness-raw-completion.json').read_text())

class ControllerTests(unittest.TestCase):
    def setup_controller(self):
        f=deepcopy(FIXTURE);clock=[f['home']['observed_at']+.3]
        p,cameras=adapter();p._geometry.clock=lambda:clock[0]
        p._geometry.pose_summary(f['home'])
        p._episode=('ep_offline','lease_offline');p._prompt='Offline completion bridge regression'
        p._history=[{'role':'system','content':'Offline regression'}]
        p._pending=dict(call_id='completed_approach',waypoint_count=68,last_step_id=67)
        cameras.position={a:[.3,0,.1] for a in ('left','right')}
        p._post_json=Mock(side_effect=[decision_response(decision(primitive=6,arm=0,gripper=0)),
            decision_response(decision(primitive=6,arm=0,gripper=1)),decision_response({**decision(),'action':'done'})])
        api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True)
        api._session_capabilities['offline']='synthetic'
        c=RunnerController(api,robot_id='robot-ba8413962083809c',share_conversation=False)
        c._provider=p;c._status='running';c._session_id='offline';c._episode_id='ep_offline';c._lease_id='lease_offline'
        c._prompt=p._prompt;c._command_step_id=68
        c._trajectory=dict(trajectory_id='approach',state='accepted',first_step_id=0,last_step_id=67,
            waypoint_count=68,progress_count=68,final_observation_received=False,final_target=f['raw_completion'])
        station={**f['raw_completion'],**f['station']};clock[0]=f['checked_at']
        c.update_monitor_observation(station)
        api.get_session=lambda session:dict(status='running',episode_id='ep_offline',lease_id='lease_offline',
            latest_observation_step=c._command_step_id,active_trajectory=None)
        api.get_robot_observation=lambda robot:deepcopy(station)
        api.stop_session=Mock(return_value={'status':'stopped'})
        sent=[]
        def wire(req,**kwargs):
            packet=json.loads(req.data);sent.append(packet)
            points=packet['waypoints']
            return io.BytesIO(json.dumps(dict(schema_version=1,accepted=True,duplicate=False,
                session_id='offline',episode_id='ep_offline',lease_id='lease_offline',trajectory_id=packet['trajectory_id'],
                first_step_id=points[0]['step_id'],last_step_id=points[-1]['step_id'],waypoint_count=len(points),dispatched_at=clock[0])).encode())
        return c,p,f,station,clock,sent,wire

    def test_raw_completion_keeps_verified_context_and_runs_two_followup_packets(self):
        c,p,f,station,clock,sent,wire=self.setup_controller()
        original=deepcopy(f['raw_completion'])
        completed=Mock(wraps=p.trajectory_completed);p.trajectory_completed=completed
        with patch('time.time',side_effect=lambda:clock[0]),patch('remote_yam.session.request.urlopen',side_effect=wire):
            c._observation({},f['raw_completion'])
            c._trajectory_result(dict(trajectory_id='approach',status='completed',step_id=67,reported_at=clock[0]))
            first=completed.call_args.args[0]
            self.assertEqual(first['source'],'hardware');self.assertTrue(first['safety']['ok'])
            self.assertFalse(first['homed']);self.assertEqual(first['observed_at'],original['observed_at'])
            self.assertEqual(first['jetson_id'],station['jetson_id'])
            for target in (0,1):
                packet=sent[-1];self.assertEqual(packet['waypoints'][-1]['left_gripper'],target)
                for point in packet['waypoints']:
                    self.assertEqual(point['left_joints_deg'],original['left_joints_deg'])
                    self.assertEqual(point['right_joints_deg'],original['right_joints_deg'])
                    self.assertEqual(point['right_gripper'],original['right_gripper'])
                tid=packet['trajectory_id']
                c._trajectory_result(dict(trajectory_id=tid,status='accepted',reported_at=clock[0]))
                for point in packet['waypoints']:
                    clock[0]+=.1;c._trajectory_progress(dict(trajectory_id=tid,step_id=point['step_id'],executed_at=clock[0]))
                final={**original,**packet['waypoints'][-1],'step_id':packet['waypoints'][-1]['step_id']+1,'observed_at':clock[0]}
                station.update(final,source='hardware',observed_at=clock[0]+.01);clock[0]+=.02
                c.update_monitor_observation(station);c._observation({},final)
                c._trajectory_result(dict(trajectory_id=tid,status='completed',step_id=final['step_id']-1,reported_at=clock[0]))
        self.assertEqual(len(sent),2);self.assertEqual(completed.call_count,3)
        self.assertEqual(f['raw_completion'],original)
        self.assertEqual(c._status,'stopped');self.assertEqual(p._outcome['status'],'done')
        self.assertEqual(p._geometry._completed_cursor,c._command_step_id)
        self.assertEqual(c._step_timings[-1]['left_displacement_m'],0.)

    def test_invalid_feedback_cannot_gain_context_or_dispatch_followup(self):
        for variant in ('estop','old_completion','wrong_robot','wrong_cursor','incomplete_progress'):
            with self.subTest(variant=variant):
                c,p,f,station,clock,sent,wire=self.setup_controller();raw=f['raw_completion']
                if variant=='estop':station['safety']={'ok':False,'estop_engaged':True}
                if variant=='old_completion':raw['observed_at']-=30
                if variant=='wrong_robot':raw['jetson_id']='another-robot'
                if variant=='wrong_cursor':raw['step_id']+=1
                if variant=='incomplete_progress':c._trajectory['progress_count']-=1
                c.update_monitor_observation(station)
                with patch('time.time',side_effect=lambda:clock[0]),patch('remote_yam.session.request.urlopen',side_effect=wire):
                    with self.assertRaises((ValueError,RuntimeError)):
                        c._observation({},raw)
                        c._trajectory_result(dict(trajectory_id='approach',status='completed',step_id=67,reported_at=clock[0]))
                self.assertEqual(sent,[]);p._post_json.assert_not_called()
                self.assertEqual(p._geometry._completed_cursor,0)

    def test_path_telemetry_is_context_free_and_cannot_change_motion_authority(self):
        c,p,f,station,clock,sent,wire=self.setup_controller()
        before={k:f['home'][k] for k in ('left_joints_deg','right_joints_deg','left_gripper','right_gripper')}
        after={k:f['raw_completion'][k] for k in before}
        identity=p._geometry._home_identity;cursor=p._geometry._completed_cursor
        with patch('time.time',side_effect=lambda:clock[0]):
            measured=p.measured_step_displacement(before,after)
        self.assertGreater(measured['left_displacement_m'],.1)
        self.assertEqual(p._geometry._home_identity,identity);self.assertEqual(p._geometry._completed_cursor,cursor)
        with self.assertRaises(ValueError):p._geometry.pose_summary(after)
        for invalid in (float('nan'),float('inf'),1e9,True):
            changed=deepcopy(after);changed['left_joints_deg'][0]=invalid
            with self.assertRaises(ValueError):p.measured_step_displacement(before,changed)
        self.assertEqual(sent,[])

if __name__=='__main__':unittest.main()
