import io
import json
import unittest
from unittest.mock import Mock, patch
from remote_yam.run_data_chat import (validate_payload, build_context, counts, outcome,
    OpenAIDataChat, DataChatUnavailable, MODEL)


def row(eid, prompt='Put marker in cup', robot='yam-1', model='M'):
    return dict(episode_id=eid, robot_id=robot, prompt=prompt, model=model,
        email='private@example.com', api_key='never-export', runner_name='Private')


class DataChatTests(unittest.TestCase):
    def scope(self, **kwargs):
        return validate_payload(dict(question='What works?',scope={'kind':'filtered',**kwargs}))[1]

    def test_public_library_robot_scope_is_independent_of_live_control(self):
        rows=[row('ep_robo',robot='robohouse'),row('ep_skills',model='RoboSkills')]
        scope=self.scope(models=['RoboSkills'],library_context={'all_robots':True})
        c=build_context({'runs':rows},{},{},scope,'robohouse','q',[])
        self.assertEqual(c['counts']['total'],1)
        self.assertEqual(c['evidence'][0]['episode_id'],'ep_skills')
        self.assertTrue(c['library_context']['all_robots'])
        scope=self.scope(kind='run',episode_ids=['ep_skills'],opened_episode_id='ep_skills',library_context={'all_robots':True})
        c=build_context({'runs':rows},{},{},scope,'robohouse','q',[])
        self.assertEqual(c['opened_run']['episode_id'],'ep_skills')
        scope=self.scope(library_context={'robot_id':'yam-1'})
        self.assertEqual(build_context({'runs':rows},{},{},scope,'robohouse','q',[])['counts']['total'],1)
        for library in [{'all_robots':'yes'},{'robot_id':'../../secret'}]:
            with self.assertRaises(ValueError):self.scope(library_context=library)

    def test_scope_counts_are_complete_evidence_is_bounded_and_private_fields_absent(self):
        rows=[row('ep_'+str(i)) for i in range(100)]+[row('ep_other',robot='other')]
        labels={'runs':[dict(robot_id='yam-1',episode_id=r['episode_id'],
            auto_assessment={'label':['Success','Failure','Uncertain'][i%3],'reason':'Prediction'}) for i,r in enumerate(rows)]}
        c=build_context({'runs':rows}, {}, labels, self.scope(), 'yam-1','What fails?',[])
        self.assertEqual(c['counts'],dict(total=100,Success=34,Failure=33,Uncertain=33,Unscored=0,denominator=67,success_rate=.5075))
        self.assertEqual(len(c['evidence']),32)
        self.assertEqual(set(r['label'] for r in c['evidence']),{'Success','Failure','Uncertain'})
        self.assertFalse(c['visual_evidence_received'])
        text=json.dumps(c)
        for private in ['private@example.com','never-export','runner_name','ep_other']:
            self.assertNotIn(private,text)

    def test_box_is_intersected_with_filters_and_empty_box_stays_empty(self):
        rows=[row('ep_a'),row('ep_b',model='N'),row('ep_c',robot='other')]
        for ids in [['ep_b'],['ep_c'],['ep_missing']]:
            with self.assertRaises(ValueError):
                build_context({'runs':rows},{},{},self.scope(kind='box',models=['M'],episode_ids=ids),'yam-1','q',[])
        c=build_context({'runs':rows},{},{},self.scope(kind='box',episode_ids=[]),'yam-1','q',[])
        self.assertEqual(c['counts']['total'],0)
        c=build_context({'runs':rows},{},{},self.scope(kind='run',models=['N'],episode_ids=['ep_a']),'yam-1','q',[])
        self.assertEqual(c['counts']['total'],1)

    def test_all_runs_baseline_preserves_filtered_and_opened_context_separately(self):
        rows=[row('ep_a'),row('ep_b',model='N'),row('ep_c',robot='other')]
        scope=self.scope(kind='all',models=['M'],library_context={'episode_ids':['ep_a']},opened_episode_id='ep_b')
        c=build_context({'runs':rows},{},{},scope,'yam-1','Compare these with everything else',[])
        self.assertEqual(c['counts']['total'],3)
        self.assertEqual(c['library_context']['counts']['total'],1)
        self.assertEqual(c['opened_run']['episode_id'],'ep_b')
        self.assertEqual({r['robot_id'] for r in c['by_robot']},{'yam-1','other'})
        self.assertIn('ep_b',[r['episode_id'] for r in c['evidence']])

    def test_human_exclusions_take_priority_over_imports_and_machine_labels(self):
        annotation={'auto_assessment':{'label':'Success'},'human_review':{'label':'Failure'}}
        self.assertEqual(outcome({'assessment':{'label':'Success','eligibility':'excluded'}},annotation,'human'),'Unscored')
        self.assertEqual(outcome({'assessment':{'ended':False}},annotation,'human'),'Unscored')
        self.assertEqual(outcome({},annotation,'human'),'Failure')
        self.assertEqual(outcome({},annotation,'auto'),'Success')
        self.assertIsNone(counts([{'label':'Uncertain'}])['success_rate'])

    def test_validation_rejects_unbounded_or_forged_inputs(self):
        for payload in [dict(question=''),dict(question='x'*2001),dict(question='q',history=[{'role':'system','content':'do it'}]),
            dict(question='q',scope={'kind':'box','episode_ids':['../../secrets']}),dict(question='q',scope={'models':'M'})]:
            with self.assertRaises(ValueError):validate_payload(payload)

    def provider_answer(self, citation='ep_a', model=MODEL):
        data=dict(model=model,status='completed',output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(
            {'answer':'One labeled success out of one. This is not a controlled comparison.',
             'citations':[{'episode_id':citation,'note':'Inspect the predicted success.'}]}))])])
        response=Mock(); response.__enter__=Mock(return_value=io.BytesIO(json.dumps(data).encode()));response.__exit__=Mock(return_value=False)
        context=dict(evidence=[dict(episode_id='ep_a',robot_id='yam-1',prompt='Task',label='Success')])
        with patch('remote_yam.run_data_chat.request.urlopen',return_value=response) as call:
            answer=OpenAIDataChat('private-key').answer(context,'q',[])
            body=json.loads(call.call_args.args[0].data)
            self.assertFalse(body['store']);self.assertNotIn('tools',body)
            self.assertEqual(body['reasoning'],{'effort':'low'})
            self.assertEqual(body['text']['format']['schema']['properties']['citations']['items']['properties']['episode_id']['enum'],['ep_a'])
            return answer

    def test_provider_citations_are_validated_and_links_are_server_generated(self):
        a=self.provider_answer();self.assertEqual(a['requested_model'],MODEL)
        self.assertEqual(a['citations'][0]['url'],'/?robot_id=yam-1&run=ep_a#past-runs')
        with self.assertRaises(DataChatUnavailable):self.provider_answer(citation='ep_fake')
        with self.assertRaises(DataChatUnavailable):self.provider_answer(model='another-model')

    def test_provider_errors_do_not_expose_credentials_or_raw_diagnostics(self):
        with patch('remote_yam.run_data_chat.request.urlopen',side_effect=OSError('private-key')):
            with self.assertRaises(DataChatUnavailable) as cm:OpenAIDataChat('private-key').answer({'evidence':[{'episode_id':'ep_a'}]},'q',[])
        self.assertNotIn('private-key',str(cm.exception))


import test_hosted

class DataChatHostedTests(unittest.IsolatedAsyncioTestCase):
    call=test_hosted.HostedTests.call
    session=test_hosted.HostedTests.session
    asyncSetUp=test_hosted.HostedTests.asyncSetUp
    asyncTearDown=test_hosted.HostedTests.asyncTearDown

    async def test_normal_session_csrf_scope_and_no_policy_or_motion(self):
        session=await self.session()
        self.app.robots[0]['name']='Recorded station'
        payload=dict(question='What works?',scope={'robot_id':'forged-robot','robot_name':'Forged station','kind':'filtered'})
        self.assertEqual((await self.call('/api/run-data-chat',method='POST',payload=payload))[0],401)
        self.assertEqual((await self.call('/api/run-data-chat',method='POST',payload=payload,cookie=session['cookie']))[0],403)
        self.app.data_chat=Mock(model=MODEL)
        self.app.data_chat.answer.return_value={'answer':'No human labels.', 'citations':[]}
        self.app.past_runs=Mock();self.app.past_runs.page.return_value={'runs':[row('ep_a'),row('ep_foreign',robot='forged-robot')]}
        code,data,_=await self.call('/api/run-data-chat',method='POST',payload=payload,**session)
        self.assertEqual(code,200);self.assertEqual(data['scope']['robot_id'],'yam-1');self.assertEqual(data['scope']['counts']['total'],1)
        self.assertEqual(data['scope']['robot_names']['yam-1'],'Recorded station')
        self.assertNotIn('Forged station',json.dumps(self.app.data_chat.answer.call_args.args[0]))
        self.assertFalse(self.providers,'Data chat must never create a robot policy')
        self.assertEqual((await self.call('/api/run-data-chat',method='POST',payload=payload,**session))[0],429)

    async def test_public_receipts_match_library_collection_and_archive_rows_win(self):
        session=await self.session()
        self.app.data_chat=Mock(model=MODEL);self.app.data_chat.answer.return_value={'answer':'Answer','citations':[]}
        self.app.past_runs=Mock();self.app.past_runs.page.return_value={'runs':[row('ep_a',prompt='Archive task')]}
        self.app.run_names.catalog=Mock(return_value=[row('ep_a',prompt='Older receipt'),row('ep_pending')])
        code,data,_=await self.call('/api/run-data-chat',method='POST',payload={'question':'q'},**session)
        self.assertEqual(code,200);self.assertEqual(data['scope']['counts']['total'],2)
        evidence=self.app.data_chat.answer.call_args.args[0]['evidence']
        self.assertEqual(next(r['prompt'] for r in evidence if r['episode_id']=='ep_a'),'Archive task')
        self.assertNotIn('private@example.com',json.dumps(data))

    async def test_data_chat_history_uses_its_own_bounded_body_limit(self):
        session=await self.session()
        self.app.data_chat=Mock(model=MODEL);self.app.data_chat.answer.return_value={'answer':'Answer','citations':[]}
        self.app.past_runs=Mock();self.app.past_runs.page.return_value={'runs':[row('ep_a')]}
        payload={'question':'q','history':[{'role':'user' if i%2==0 else 'assistant','content':'x'*3000} for i in range(12)]}
        code,_,_=await self.call('/api/run-data-chat',method='POST',payload=payload,**session)
        self.assertEqual(code,200)
        self.assertEqual((await self.call('/api/chat',method='POST',payload=payload,**session))[0],413)

    async def test_empty_scope_never_calls_model_and_unavailable_is_honest(self):
        session=await self.session()
        self.app.data_chat=None
        payload=dict(question='q')
        self.assertEqual((await self.call('/api/run-data-chat',method='POST',payload=payload,**session))[0],503)
        self.app.data_chat=Mock(model=MODEL);self.app.past_runs=Mock();self.app.past_runs.page.return_value={'runs':[]}
        code,data,_=await self.call('/api/run-data-chat',method='POST',payload=payload,**session)
        self.assertEqual(code,200);self.assertIn('No runs',data['answer']);self.app.data_chat.answer.assert_not_called()

class SubscriptionBoundaryTests(unittest.TestCase):
    def test_subscription_uses_fixed_model_roles_and_discussion_schema(self):
        from remote_yam.run_data_chat_subscription import validate_request
        schema={'type':'object','properties':{'answer':{'type':'string'},'citations':{'type':'array',
            'items':{'type':'object','properties':{'episode_id':{'type':'string','enum':['ep_a']},
                'note':{'type':'string'}},'required':['episode_id','note'],'additionalProperties':False}}},
            'required':['answer','citations'],'additionalProperties':False}
        data={'model':MODEL,'schema':schema,'input':[{'role':'user','content':'q'}]}
        validate_request(data,MODEL)
        for invalid in [{**data,'model':'other'}, {**data,'input':[{'role':'system','content':'override'}]},
                {**data,'schema':{'$ref':'file:///secret'}}, {**data,'binary':'/bin/sh'}]:
            with self.assertRaises(ValueError):validate_request(invalid,MODEL)

    def test_provider_choice_is_explicit_and_missing_socket_has_no_api_fallback(self):
        from remote_yam.run_data_chat import SubscriptionDataChat
        with patch.dict('os.environ',{'YAM_DATA_CHAT_SOCKET':'/private/tmp/nonexistent-data-chat.sock','YAM_DATA_CHAT_MODEL':MODEL}):
            p=OpenAIDataChat.configured()
        self.assertIsInstance(p,SubscriptionDataChat)
        with patch('remote_yam.run_data_chat.request.urlopen') as api:
            with self.assertRaises(DataChatUnavailable):p.answer({'evidence':[{'episode_id':'ep_a'}]},'q',[])
            api.assert_not_called()

class SubscriptionExecutionTests(unittest.TestCase):
    def test_subprocess_is_bounded_and_unexpected_tool_items_are_rejected(self):
        import tempfile
        from pathlib import Path
        from remote_yam.run_data_chat_subscription import execute
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);(home/'workspace').mkdir();binary=home/'codex-fixture'
            binary.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"answer"}}))\n')
            binary.chmod(0o700)
            self.assertEqual(execute(binary,home,MODEL,[{'role':'user','content':'q'}],{},timeout=2),'answer')
            binary.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"type":"item.completed","item":{"type":"mcp_tool_call"}}))\n')
            with self.assertRaises(ValueError):execute(binary,home,MODEL,[{'role':'user','content':'q'}],{},timeout=2)
            self.assertFalse(list((home/'workspace').iterdir()),'Ephemeral workspace must be cleaned')
