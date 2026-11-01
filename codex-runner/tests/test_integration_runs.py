"""Public integration receipts reach the real catalog and immutable media routes."""
import asyncio
import hashlib
import json
import shutil
from urllib.parse import urlencode

import pytest

from playground import HostedRunner
from remote_yam.integration_runs import IntegrationRuns, PublicRunSource
from remote_yam.past_runs import PastRuns, RunNames
from remote_yam.session import MockSessionAPI

ROBOT = 'robot-example'
MODEL = 'spotter/dreamlabs/dream-1-beta'


@pytest.fixture
def source(tmp_path):
    database, replay_root = tmp_path/'runs.sqlite3', tmp_path/'replays'
    replay_root.mkdir()
    names = RunNames(database)
    names.remember('ep_spotter', 'Andrew')
    names.remember_metadata('ep_spotter', ROBOT, 'orange block into cup', 20,
        {'model':MODEL, 'api_key':'PRIVATE-KEY', 'email':'private@example.invalid'})
    names.remember_result('ep_spotter', {'status':'timed_out'})
    names.remember_metadata('ep_other', 'other-robot', 'wrong station', 30, {'model':'other'})
    body = b'fixture immutable media bytes'
    digest = hashlib.sha256(body).hexdigest()
    (replay_root/'ep_spotter').mkdir()
    (replay_root/'ep_spotter'/(digest+'.mp4')).write_bytes(body)
    (replay_root/'ep_spotter.json').write_text(json.dumps({
        'episode_id':'ep_spotter', 'robot_id':ROBOT, 'bytes':len(body),
        'preview':{'sha256':digest, 'duration_s':12, 'speed':1, 'camera_order':['left','top','right']}}))
    return dict(database=str(database), replay_root=str(replay_root), robot_id=ROBOT), names, body, digest


def archive_reader(path):
    if path == 'meta/blupe_source_episodes.jsonl':
        return json.dumps({'episode_id':'ep_archive', 'episode_index':0, 'recorded_at':10, 'robot_id':ROBOT})
    if path == 'meta/episodes.jsonl':
        return json.dumps({'episode_index':0, 'tasks':['old task']})
    return '{}'


def test_existing_and_new_receipts_merge_with_real_archive_filters(source):
    config, names, _, _ = source
    catalog = IntegrationRuns(PastRuns(archive_reader, robot_id=None), [config])
    before = catalog.page()
    assert [r['episode_id'] for r in before['runs']] == ['ep_spotter','ep_archive']
    row = before['runs'][0]
    assert (row['runner_name'],row['model'],row['result']) == ('Andrew',MODEL,'Stopped')
    assert row['preview_speed'] == 1 and row['video_status'] == 'ready'
    assert catalog.page(model=MODEL)['total'] == 1
    assert catalog.page(models=[MODEL],metadata=True)['total'] == 1
    assert catalog.page(metadata=True)['runs'][0]['video_status'] == 'ready'
    assert catalog.page(query='orange block')['runs'][0]['episode_id'] == 'ep_spotter'
    assert catalog.page(robot_id='other-robot')['runs'] == []
    assert catalog.page(episode_ids={'ep_spotter'})['total'] == 1
    assert 'PRIVATE' not in json.dumps(before) and 'private@example' not in json.dumps(before)
    names.remember_metadata('ep_next',ROBOT,'new run',40,{'model':MODEL})
    new = catalog.page()['runs'][0]
    assert new['episode_id'] == 'ep_next' and new['video_status'] == 'processing'
    assert new['video_url'] is None and new['result'] == 'Unknown'
    assert catalog.get('ep_spotter')['video_status'] == 'ready'


def test_published_duplicate_is_enriched_once_without_erasing_spotter_identity(source):
    config, _, _, _ = source
    def reader(path):
        return archive_reader(path).replace('ep_archive','ep_spotter')
    catalog = IntegrationRuns(PastRuns(reader,robot_id=None),[config])
    page = catalog.page()
    assert page['total'] == 1
    assert page['runs'][0]['model'] == MODEL
    assert page['runs'][0]['prompt'] == 'orange block into cup'
    assert page['runs'][0]['result_reason'] == 'Run reached time limit'

    # A legacy receipt without a model must preserve the archive's recorded one.
    import sqlite3
    with sqlite3.connect(config['database']) as db:
        db.execute('DELETE FROM run_configuration')
    real = catalog.archive
    original_page = real.page
    real.page = lambda **kwargs: dict(original_page(**kwargs),runs=[{
        'episode_id':'ep_spotter','robot_id':ROBOT,'started_at':10,'model':'archived-method','prompt':'task'}])
    assert catalog.page()['runs'][0]['model'] == 'archived-method'


def test_archive_failure_does_not_hide_integration_and_missing_source_is_not_created(source,tmp_path):
    config, names, _, _ = source
    def unavailable(path):
        raise OSError('archive unavailable')
    catalog = IntegrationRuns(PastRuns(unavailable,robot_id=None),[config])
    page = catalog.page(metadata=True)
    assert page['stale'] and page['total'] == 1
    names.remember_metadata('ep_pending',ROBOT,'new task',50,{'model':MODEL})
    assert catalog.get('ep_pending')['video_status'] == 'processing'
    missing = tmp_path/'missing.sqlite3'
    assert PublicRunSource(missing,tmp_path,ROBOT).rows() == {}
    assert not missing.exists()
    # A broken source does not take the existing public archive down.
    corrupt = tmp_path/'broken.sqlite3'
    corrupt.write_bytes(b'invalid sqlite')
    good = IntegrationRuns(PastRuns(archive_reader,robot_id=None),[dict(config,database=str(corrupt))])
    assert good.page()['total'] == 1


def test_media_requires_owned_receipt_valid_hash_and_honors_range(source):
    config, _, body, digest = source
    public = PublicRunSource(**config)
    assert public.video('ep_spotter',digest,'bytes=3-8')[:2] == (206,body[3:9])
    assert public.video('ep_spotter',digest,'bytes=-4')[:2] == (206,body[-4:])
    assert public.video('ep_spotter',digest,'bytes=999-')[0] == 416
    assert public.video('ep_spotter',digest,'bytes=-0')[0] == 416
    assert public.video('ep_spotter','0'*64) is None
    assert public.video('../ep_spotter',digest) is None
    assert public.video('ep_other',digest) is None
    path = public.replay_root/'ep_spotter'/(digest+'.mp4')
    path.write_bytes(b'x'*len(body))
    assert public.video('ep_spotter',digest) is None


async def call(app,path,query='',headers=()):
    messages=[]
    async def receive():
        return {'type':'http.request','body':b'', 'more_body':False}
    async def send(value):
        messages.append(value)
    await app({'type':'http','method':'GET','path':path,'query_string':query.encode(),
        'headers':[(b'host',b'robot.example'),*headers]},receive,send)
    return messages[0]['status'],b''.join(m.get('body',b'') for m in messages),dict(messages[0]['headers'])


def test_normal_http_catalog_detail_and_replay_preserve_public_attribution(source,tmp_path,monkeypatch):
    config, names, body, digest = source
    monkeypatch.setenv('YAM_PUBLIC_RUN_SOURCES',json.dumps([config]))
    monkeypatch.setenv('YAM_RUN_NAMES_DATABASE',str(tmp_path/'main-runs.sqlite3'))
    app=HostedRunner(public_origin='https://robot.example',session_api='https://session.example',
        camera_origin='https://session.example',api_factory=MockSessionAPI)
    try:
        assert isinstance(app.past_runs,IntegrationRuns)
        app.past_runs.archive.reader=archive_reader
        monkeypatch.setattr(app.task_cloud,'schedule',lambda rows:None)
        monkeypatch.setattr(app.task_cloud,'snapshot',lambda rows:{'coordinates':{}})
        paths = [('/api/past-runs',urlencode({'model':MODEL})),
                 ('/api/past-runs','episode_id=ep_spotter'),
                 ('/api/run-catalog',urlencode({'model':MODEL})),
                 ('/api/run-catalog',urlencode({'view':'cloud','model':MODEL}))]
        for path,query in paths:
            status,raw,_=asyncio.run(call(app,path,query))
            assert status == 200,raw
            data=json.loads(raw)
            assert len(data['runs']) == 1
            if 'total' in data:
                assert data['total'] == 1
            row=data['runs'][0]
            assert row['model'] == MODEL and row['runner_name'] == 'Andrew'
            assert 'private@example' not in raw.decode() and 'PRIVATE-KEY' not in raw.decode()
        url=app.past_runs.get('ep_spotter')['video_url']
        status,raw,headers=asyncio.run(call(app,url,headers=[(b'range',b'bytes=2-6')]))
        assert (status,raw) == (206,body[2:7])
        assert headers[b'content-range'] == f'bytes 2-6/{len(body)}'.encode()
        assert b"media-src 'self'" in headers[b'content-security-policy']
        assert asyncio.run(call(app,'/api/integration-replays/ep_spotter/'+'0'*64+'.mp4'))[0] == 404
        assert not app.visitors and not (tmp_path/'main-runs.sqlite3').exists()
    finally:
        getattr(app.past_runs,'archive',app.past_runs).detail_pool.shutdown(wait=True)
        shutil.rmtree(app.root)
