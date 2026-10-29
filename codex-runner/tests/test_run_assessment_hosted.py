import json
from unittest.mock import Mock
import unittest
from urllib.parse import urlencode
import test_hosted
from remote_yam.run_assessments import RunAssessments


class AssessmentHostedTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_hosted.HostedTests.asyncSetUp
    asyncTearDown = test_hosted.HostedTests.asyncTearDown
    call = test_hosted.HostedTests.call
    session = test_hosted.HostedTests.session

    async def catalog(self, query=''):
        sent=[]
        async def receive(): return {'type':'http.request','body':b''}
        async def send(value): sent.append(value)
        await self.app({'type':'http','method':'GET','path':'/api/run-catalog','query_string':query.encode(),
                        'headers':[(b'host',b'robot.example')]},receive,send)
        return sent[0]['status'],json.loads(sent[-1]['body'])

    async def test_real_session_ownership_later_same_user_and_revision_scoped_review(self):
        self.app.run_assessments=RunAssessments(self.app.root/'assessment-tests.sqlite3')
        runner=await self.session(); owner=list(self.app.visitors.values())[-1]
        owner.recorded_user_id='existing-account'
        owner.runner_session_id='trusted-session';owner.runner_task='Move marker'
        owner.controller.status=Mock(return_value={'episode_id':'ep_one','session_id':'trusted-session','status':'running'})
        self.app.remember_runner(owner)
        self.app.remember_assessment_owner(owner)
        payload={'episode_id':'ep_one','operation':'assess','label':'Success','revision':0}
        self.assertEqual((await self.call('/api/run-assessment',method='POST',payload=payload))[0],401)
        self.assertEqual((await self.call('/api/run-assessment',method='POST',payload=payload,cookie=runner['cookie'],csrf='wrong'))[0],403)
        code,body,_=await self.call('/api/run-assessment',method='POST',payload=payload,**runner)
        self.assertEqual((code,body['eligibility']),(200,'provisional'))
        owner.controller.status.return_value['status']='stopped'
        other=await self.session()
        vote={'episode_id':'ep_one','operation':'vote','vote':-1,'revision':1}
        self.assertEqual((await self.call('/api/run-assessment',method='POST',payload=vote,**runner))[0],403)
        code,body,_=await self.call('/api/run-assessment',method='POST',payload=vote,**other)
        self.assertEqual((code,body['eligibility'],body['label']),(200,'excluded','Success'))
        payload.update(label='Failure',revision=1)
        self.assertEqual((await self.call('/api/run-assessment',method='POST',payload=payload,**other))[0],403)
        new=await self.session();list(self.app.visitors.values())[-1].recorded_user_id='existing-account'
        code,body,_=await self.call('/api/run-assessment',method='POST',payload=payload,**new)
        self.assertEqual((code,body['revision'],body['incorrect']),(200,2,0))
        self.assertEqual(body['history'][1]['incorrect'],1)
        self.assertEqual((await self.call('/api/run-assessment',method='POST',payload=vote,**other))[0],409)

    async def test_catalog_scores_complete_dataset_no_media_preloads_and_model_versions(self):
        self.app.run_assessments=RunAssessments(self.app.root/'catalog-tests.sqlite3')
        archive=self.app.past_runs
        archive.rows=[{'episode_id':f'ep_{i}','robot_id':'yam-1','prompt':'Put pens in cup','started_at':i,
                       'episode_index':i,'model':'M' if i<204 else 'Other','model_version':'v1' if i%2 else 'v2'} for i in range(205)]
        import time
        archive.updated=time.monotonic();archive.model_reader=lambda:{}
        for i in range(205):
            self.app.run_assessments.register(f'ep_{i}','runner',ended=True)
            self.app.run_assessments.assess(f'ep_{i}','Success' if i<3 else 'Failure',0,'runner')
        archive.reader=Mock(side_effect=AssertionError('Metadata listing must not preload media/detail'))
        code,body=await self.catalog('model=M&q=pen&offset=100')
        self.assertEqual(code,200);self.assertEqual(len(body['runs']),100)
        self.assertEqual(body['total'],204)
        self.assertEqual(sum(score['denominator'] for score in body['scores']),204)
        self.assertEqual(sum(score['successes'] for score in body['scores']),3)
        self.assertEqual({score['version'] for score in body['scores']},{'v1','v2'})
        self.assertIn('search_match',body['runs'][0]);self.assertNotIn('video_url',body['runs'][0])
        self.assertNotIn('owner_session',json.dumps(body))
        archive.reader.assert_not_called()
        code,body=await self.catalog('model=M&model=Other')
        self.assertEqual((code,body['total']),(200,205))
        for query in ['offset=-1','view=2d',urlencode({'q':'x'*301}),urlencode({'model':'x'*129})]:
            self.assertEqual((await self.catalog(query))[0],400)

    async def test_cloud_limit_and_zero_matching_model_scores_use_full_metadata(self):
        import time
        self.app.past_runs.rows=[{'episode_id':f'ep_scale_{i}','episode_index':i,'robot_id':'yam-1',
            'prompt':'A public task','model':'M','model_version':'v1','started_at':i} for i in range(10005)]
        self.app.past_runs.updated=time.monotonic();self.app.past_runs.model_reader=lambda:{}
        self.app.task_cloud=Mock()
        self.app.task_cloud.snapshot.return_value={'status':'ready','version':'test-map','coordinates':{}}
        code,body=await self.catalog('view=cloud&model=M')
        self.assertEqual((code,len(body['runs']),body['total'],body['sampled']),(200,10000,10005,True))
        self.assertEqual(body['scores'][0]['unlabeled'],10005)
        self.assertIsNone(body['scores'][0]['rate'])
        code,missing=await self.catalog('model=M&model=NoRecords')
        self.assertEqual(next(s for s in missing['scores'] if s['model']=='NoRecords')['denominator'],0)
        code,body=await self.catalog('model=M&q=nonmatchingword')
        self.assertEqual((code,body['total'],body['scores'][0]['denominator']),(200,0,0))
        self.assertEqual(body['scores'][0]['model'],'M')
        self.assertIsNone(body['scores'][0]['rate'])
