"""Import real public receipt shapes without mislabeling methods or private data."""
import asyncio
import io
import json
import shutil
import sqlite3
from urllib.error import HTTPError

import pytest

from playground import HostedRunner
from remote_yam.integration_runs import IntegrationRuns, PublicRunSource
from remote_yam.past_runs import PastRuns
from remote_yam.public_history import NoRedirect, project_runs, read_runs, save_receipts
from remote_yam.session import MockSessionAPI

SCOPE = dict(origin='https://skills.example', approach='RoboSkills', robot_id='yam-1')


def run(eid='ep_roboskills'):
    return {'id':'site-run', 'approach':'RoboSkills', 'robot':'yam-1', 'execution':'physical',
        'instruction':'Place the block on the plate', 'runnerName':'Researcher',
        'runnerEmail':'PRIVATE@example.invalid', 'owner':'PRIVATE-ACCOUNT',
        'result':{'episode_id':eid, 'approach':'RoboSkills', 'robot_id':'yam-1',
            'run_started_at':100, 'inference_model':'gpt-6-sol',
            'inference_models':{'initial':'gpt-6-sol', 'subsequent':'gpt-6-astra'},
            'lease_id':'PRIVATE-CAPABILITY', 'provider':{'api_key':'PRIVATE-KEY'}}}


def reader(path):
    if path == 'meta/blupe_source_episodes.jsonl':
        return json.dumps({'episode_id':'ep_roboskills','episode_index':7,'recorded_at':100})
    if path == 'meta/episodes.jsonl':
        return json.dumps({'episode_index':7,'tasks':['Place the block on the plate']})
    if path.startswith('meta/'):
        return ''
    return json.dumps({'outcome':'policy_complete','video':{'duration_s':3}})


def test_recorded_approach_is_separate_from_underlying_models_and_private_fields(tmp_path):
    receipts = project_runs([run()], **SCOPE)
    assert receipts[0]['configuration']['model'] == 'RoboSkills'
    assert receipts[0]['configuration']['inference_model'] == 'gpt-6-sol'
    assert receipts[0]['configuration']['inference_models']['subsequent'] == 'gpt-6-astra'
    assert 'PRIVATE' not in json.dumps(receipts)
    database = tmp_path/'history.sqlite3'
    assert save_receipts(database, receipts, **SCOPE) == 1
    with sqlite3.connect(database) as db:
        exported = list(db.iterdump())
    assert 'PRIVATE' not in json.dumps(exported)
    assert database.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('field,value', [
    ('approach','Other'), ('robot','other-robot'), ('execution','simulation'),
    ('runnerName',''), ('instruction',''), ('result.episode_id','../ep_bad'),
    ('result.episode_id',None), ('result.approach','Other'),
    ('result.robot_id','other-robot'), ('result.run_started_at',float('nan')),
    ('result.run_started_at',True), ('result.run_started_at',None),
])
def test_missing_or_conflicting_provenance_is_never_guessed(field,value):
    item=run()
    if field.startswith('result.'):
        item['result'][field.split('.')[1]]=value
    else:
        item[field]=value
    assert project_runs([item],**SCOPE) == []


def test_source_cache_is_idempotent_preserves_history_and_rejects_other_databases(tmp_path):
    database=tmp_path/'history.sqlite3'
    receipts=project_runs([run()],**SCOPE)
    assert save_receipts(database,receipts,**SCOPE) == 1
    assert save_receipts(database,receipts,**SCOPE) == 1
    assert save_receipts(database,project_runs([run('ep_new')],**SCOPE),**SCOPE) == 2
    assert save_receipts(database,[],**SCOPE) == 2  # Paged source no longer returns old receipts.
    with pytest.raises(ValueError,match='different source'):
        save_receipts(database,[],**dict(SCOPE,approach='Other'))
    existing=tmp_path/'unrelated.sqlite3'
    with sqlite3.connect(existing) as db:
        db.execute('CREATE TABLE owner_data (value TEXT)')
        db.execute("INSERT INTO owner_data VALUES ('retain')")
    before=existing.read_bytes()
    with pytest.raises(ValueError,match='dedicated'):
        save_receipts(existing,receipts,**SCOPE)
    assert existing.read_bytes() == before


def test_public_method_label_survives_catalog_filters_detail_and_future_import(tmp_path):
    database=tmp_path/'history.sqlite3'
    # The archived episode has no method label before the provenance import.
    archive=PastRuns(reader,robot_id=None)
    assert archive.page(model='RoboSkills')['runs'] == []
    save_receipts(database,project_runs([run()],**SCOPE),**SCOPE)
    # Existing positional source callers retain their robot/replay-root scope.
    assert list(PublicRunSource(database,tmp_path/'no-clips','yam-1').rows()) == ['ep_roboskills']
    catalog=IntegrationRuns(archive,[dict(database=str(database),robot_id='yam-1')])
    row=catalog.page(model='RoboSkills')['runs'][0]
    assert row['model'] == 'RoboSkills' and row['runner_name'] == 'Researcher'
    assert row['result'] == 'Success'  # Archive outcome/media remain authoritative.
    assert row['video_url'].endswith('videos/ep_roboskills.mp4')
    assert catalog.get('ep_roboskills')['model'] == 'RoboSkills'
    assert catalog.page(metadata=True,models=['RoboSkills'])['total'] == 1
    save_receipts(database,project_runs([run('ep_future')],**SCOPE),**SCOPE)
    assert catalog.page(model='RoboSkills')['total'] == 2
    new=catalog.get('ep_future')
    assert new['model'] == 'RoboSkills' and new['video_status'] == 'processing'
    archive.detail_pool.shutdown(wait=True)


def test_service_access_is_origin_scoped_bounded_and_does_not_follow_redirects(monkeypatch):
    captured=[]
    class Opener:
        def open(self,request,timeout):
            captured.append((request,timeout))
            return io.BytesIO(json.dumps({'runs':[run()]}).encode())
    monkeypatch.setattr('remote_yam.public_history.build_opener',lambda handler:Opener())
    assert len(read_runs(SCOPE['origin'],'PRIVATE-TOKEN')) == 1
    request,timeout=captured[0]
    assert request.full_url == 'https://skills.example/api/physical/runs' and timeout == 20
    assert dict(request.header_items())['Oai-sites-authorization'] == 'Bearer PRIVATE-TOKEN'
    with pytest.raises(HTTPError):
        NoRedirect().redirect_request(request,None,302,'redirect',{},'https://other.example/')
    for origin in ['http://skills.example','https://name:secret@skills.example','https://skills.example/path']:
        with pytest.raises(ValueError):
            read_runs(origin,'PRIVATE-TOKEN')
    monkeypatch.setattr('remote_yam.public_history.MAX_BYTES',1)
    with pytest.raises(ValueError,match='too large'):
        read_runs(SCOPE['origin'])


def test_normal_http_history_catalog_cloud_and_replay_details_show_roboskills(tmp_path,monkeypatch):
    database=tmp_path/'history.sqlite3'
    save_receipts(database,project_runs([run()],**SCOPE),**SCOPE)
    monkeypatch.setenv('YAM_PUBLIC_RUN_SOURCES',json.dumps([dict(database=str(database),robot_id='yam-1')]))
    monkeypatch.setenv('YAM_RUN_NAMES_DATABASE',str(tmp_path/'main.sqlite3'))
    app=HostedRunner(public_origin='https://robot.example',session_api='https://session.example',
        camera_origin='https://session.example',api_factory=MockSessionAPI)
    app.past_runs.archive.reader=reader
    monkeypatch.setattr(app.task_cloud,'schedule',lambda rows:None)
    monkeypatch.setattr(app.task_cloud,'snapshot',lambda rows:{'coordinates':{}})
    async def call(path,query):
        messages=[]
        async def receive():return {'type':'http.request','body':b''}
        async def send(m):messages.append(m)
        await app({'type':'http','method':'GET','path':path,'query_string':query.encode(),
            'headers':[(b'host',b'robot.example')]},receive,send)
        assert messages[0]['status'] == 200,messages
        return json.loads(b''.join(m.get('body',b'') for m in messages))
    try:
        for path,query in [('/api/past-runs','model=RoboSkills'),
                ('/api/past-runs','episode_id=ep_roboskills'),
                ('/api/run-catalog','model=RoboSkills'),
                ('/api/run-catalog','model=RoboSkills&view=cloud')]:
            data=asyncio.run(call(path,query))
            assert len(data['runs']) == 1
            assert data['runs'][0]['model'] == 'RoboSkills'
            assert data['runs'][0]['runner_name'] == 'Researcher'
            assert 'PRIVATE' not in json.dumps(data)
        assert not app.visitors
    finally:
        app.past_runs.archive.detail_pool.shutdown(wait=True)
        shutil.rmtree(app.root)
