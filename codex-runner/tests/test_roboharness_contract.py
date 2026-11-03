import io
import json
import unittest
from unittest.mock import patch
import numpy as np

from remote_yam.roboharness_contract import NAMES,SCHEMA,decision_response
from remote_yam.roboharness_control import RoboHarnessControl,InputRejected
from remote_yam.session import HttpSessionAPI
from test_roboharness_control import observation


def decision(**targets):
    return dict(action='move_to',targets={k:targets.get(k) for k in NAMES},note='Offline geometric tool test',summary='',reason='',hindsight='')


class ParserWireTests(unittest.TestCase):
    def test_actual_parser_generator_serializer_and_canonical_validator(self):
        obs=observation();control=RoboHarnessControl(obs['robot_id'])
        pose=control.pose_summary(obs)
        api=HttpSessionAPI('https://offline.invalid',supports_trajectories=True)
        api._session_capabilities['offline']='synthetic'
        for arm,name in enumerate(('left','right')):
            for fraction in (0.,1.,.27):
                with self.subTest(arm=name,fraction=fraction):
                    decoded=decision_response(decision(primitive=6,arm=arm,gripper=fraction))['output'][0]
                    args=json.loads(decoded['arguments']);args.pop('note')
                    packet=control.build({'kind':decoded['name'],**args},obs,0)
                    sent=[]
                    def wire(req,**_):sent.append(json.loads(req.data));return io.BytesIO(b'{"accepted":true}')
                    with patch('remote_yam.session.request.urlopen',side_effect=wire):
                        api.submit_trajectory('offline','ep_offline','lease_offline','traj_offline',10,packet)
                    self.assertEqual(len(sent),1);self.assertEqual(sent[0]['waypoints'][-1][name+'_gripper'],fraction)

    def test_invalid_numeric_envelope_is_rejected_before_any_wire(self):
        invalid=[decision(primitive=6,arm=0,gripper=-1e-16),decision(primitive=6,arm=0,gripper=1+1e-15),
            decision(primitive=1,point_a=0,u=float('nan'),v=100),decision(primitive=1,point_a=16,u=1,v=1),
            decision(primitive=6,arm=True,gripper=0),decision(primitive=6,arm=.5,gripper=0),
            decision(primitive=6,arm=0,gripper=0,x=0),decision(primitive=100,arm=0)]
        with patch('remote_yam.session.request.urlopen') as wire:
            for value in invalid:
                with self.subTest(value=value),self.assertRaises(InputRejected):decision_response(value)
            wire.assert_not_called()

    def test_terminal_output_and_tracking_touch_are_distinct(self):
        value=decision();value['action']='done';value['summary']='Observed object placed'
        self.assertEqual(decision_response(value)['output'][0]['name'],'done')
        value['targets']['x']=0
        with self.assertRaises(InputRejected):decision_response(value)
        value=decision(primitive=2,arm=1,point_a=0,u=1000,v=0,x=0,y=0,z=.05)
        call=decision_response(value)['output'][0];args=json.loads(call['arguments'])
        self.assertEqual(call['name'],'touch');self.assertEqual(args['arm'],'right')
        self.assertEqual(args['register'],{'u':1000.,'v':0.})
        self.assertEqual(args['point_ids'],['point_0'])


if __name__=='__main__':unittest.main()
