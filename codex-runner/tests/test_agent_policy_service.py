import io
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from remote_yam.agent_policy_service import AgentPolicyService, configure
from remote_yam.providers import PolicyComplete
from remote_yam.steering import SteeringInbox


def observation(step=0):
    return dict(episode_id='episode', lease_id='lease', step_id=step, observed_at=123., settled=True)


class AgentServiceTests(unittest.TestCase):
    def provider(self):
        return AgentPolicyService('http://127.0.0.1:8798', 'private-token-'+'x'*32,
                                  robot_id='yam-1', namespace='a'*64)

    def test_only_configured_secure_origins_and_model_are_accepted(self):
        for url in ('http://remote.example','https://user:pass@example.com','https://example.com/path'):
            with self.assertRaises(ValueError):
                AgentPolicyService(url,'x'*32,robot_id='yam-1',namespace='a'*64)
        with tempfile.TemporaryDirectory() as root:
            token=Path(root)/'token';token.write_text('x'*32)
            app=SimpleNamespace(root=Path(root),hardware='yam',robot_id='yam-1',extra_providers={})
            configure(app,'http://127.0.0.1:8798',str(token),'gpt-6-astra')
            self.assertEqual(set(app.extra_providers),{'agent_as_policy','agent_as_policy_memo'})
            one=app.extra_providers['agent_as_policy_memo']('',Path(root))
            two=app.extra_providers['agent_as_policy_memo']('',Path(root))
            self.assertNotEqual(one.namespace,two.namespace)  # even with one shared recordings directory
            with self.assertRaises(ValueError): app.extra_providers['agent_as_policy_memo']('foreign-model',Path(root))

    def test_packet_completion_and_worker_finish_use_existing_controller_cursor(self):
        provider=self.provider();requests=[]
        responses=[{'id':'b'*32},{'status':'running','packet':{'id':'1','points':[{'step_id':0}]}},
                   {'status':'completed','outcome':{'summary':'done'}}]
        def fetch(path,value=None): requests.append((path,value));return responses.pop(0)
        provider._request=fetch
        self.assertEqual(provider.build_trajectory('task',observation(),0),[{'step_id':0}])
        with self.assertRaises(RuntimeError): provider.trajectory_completed(observation(2),1)
        provider.trajectory_completed(observation(1),1)
        with self.assertRaises(PolicyComplete): provider.build_trajectory('task',observation(1),1)
        self.assertEqual(requests[2][1]['acknowledgement'],'1')
        self.assertNotIn('session_capability',json.dumps(requests))

    def test_correction_receipt_waits_for_observation_delivery(self):
        provider=self.provider();events=[]
        provider.steering=SteeringInbox(lambda *a,**kw:events.append((a,kw)))
        provider.steering.submit('Go above the rim.','correction_request_01')
        provider._run_id='b'*32
        calls=[]
        def poll(path,value):
            calls.append(value)
            return dict(status='running',packet={'id':'1','points':[{'step_id':0}]},
                        delivered_corrections=['correction_request_01'])
        provider._request=poll
        provider.build_trajectory('task',observation(),0)
        self.assertEqual(calls[0]['corrections'][0]['text'],'Go above the rim.')
        self.assertEqual(provider.steering.snapshot()[0]['state'],'included')
        self.assertFalse(provider.steering.pending())

    def test_memory_identity_survives_new_sessions_and_isolates_other_browsers(self):
        from http.cookies import SimpleCookie
        from remote_yam.agent_policy_service import memory_identity
        app=SimpleNamespace(cookie_name='__Host-yam-visitor',robot_id='yam-1',secure=True)
        first,again,other=SimpleNamespace(),SimpleNamespace(),SimpleNamespace()
        _,header=memory_identity(app,SimpleCookie(),first)
        cookies=SimpleCookie();cookies.load(header.decode())
        memory_identity(app,cookies,again)
        memory_identity(app,SimpleCookie(),other)
        self.assertEqual(first.agent_memory_namespace,again.agent_memory_namespace)
        self.assertNotEqual(first.agent_memory_namespace,other.agent_memory_namespace)
        self.assertIn(b'HttpOnly',header);self.assertIn(b'Secure',header)

    def test_failed_packet_cancels_worker_without_replay_or_secret_in_config(self):
        provider=self.provider();provider._run_id='b'*32;calls=[]
        provider._request=lambda path,payload:calls.append(path) or {}
        provider.trajectory_failed('timeout','unknown completion',1)
        self.assertEqual(calls,['/runs/'+'b'*32+'/stop'])
        with self.assertRaises(RuntimeError): provider.build_trajectory('task',observation(),0)
        self.assertNotIn('private-token',json.dumps(provider.public_config()))


if __name__=='__main__': unittest.main()
