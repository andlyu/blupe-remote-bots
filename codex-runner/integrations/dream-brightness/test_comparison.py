import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from comparison import ExperimentStore, run_record, summarize
from serve import make_runner_type, runner_root


def record(episode, factor, **changes):
    state = dict(episode_id=episode, provider={'provider':'dream', 'model':'dreamlabs/dream-1-beta',
        'image_experiment':{'brightness_factor':factor}, 'api_key':'never-retain'},
        run_duration_s=120, run_started_at=100., run_ended_at=220., status='stopped',
        run_configuration={'task_prompt':'Put pens in cup', 'code_revision':'runner-revision'},
        run_metrics={'model_calls':0, 'model_s':0.}, latency={'model':{'count':4,'avg_ms':2000}}, packets_submitted=4,
        email='private@example.com', session_id='private-session', lease_id='private-capability')
    state.update(changes)
    return run_record(state, robot_id='yam-1', task='fallback', runner_name='Confirmed researcher')


def included(label):
    return {'label':label, 'eligibility':'included', 'ended':True}


def test_retains_separate_episodes_and_rejects_relabeling(tmp_path):
    store = ExperimentStore(tmp_path / 'experiment.sqlite3')
    first, second = record('ep_baseline', 1), record('ep_dark', .5)
    store.remember(first)
    store.remember(second)
    assert len(store.records()) == 2
    for value in store.records():
        assert 'private' not in json.dumps(value)
        assert 'never-retain' not in json.dumps(value)
    with pytest.raises(ValueError, match='condition changed'):
        store.remember({**first, 'brightness_factor':.5})
    assert next(value for value in store.records() if value['episode_id'] == 'ep_baseline')['brightness_factor'] == 1


def test_only_ended_human_labels_score_and_revisions_change_comparison():
    records = [record('ep_base', 1), record('ep_dark', .5), record('ep_unscored', .5), record('ep_active', .5)]
    labels = {'ep_base':included('Success'), 'ep_dark':included('Failure'),
              'ep_active':{'label':'Success', 'eligibility':'included', 'ended':False}}
    group = summarize(records, labels)['groups'][0]
    assert group['difference_percentage_points'] == -100
    dark = group['variants'][1]
    assert (dark['runs'], dark['scored'], dark['unscored']) == (3, 1, 2)
    assert dark['mean_model_call_s'] == 2
    labels['ep_dark'] = included('Success')
    assert summarize(records, labels)['groups'][0]['difference_percentage_points'] == 0
    labels['ep_dark'] = {'label':'Success', 'eligibility':'excluded', 'ended':True}
    group = summarize(records, labels)['groups'][0]
    assert group['difference_percentage_points'] is None
    assert group['variants'][1]['excluded'] == 1


@pytest.mark.parametrize('field,value', [('robot_id','other-robot'), ('model','dreamlabs/dream-1-beta-flash'),
    ('task','Different task'), ('duration_s',60), ('code_revision','new-control'), ('experiment_revision','new-transform'),
    ('calibration_fingerprint','new-selected-profile')])
def test_incomparable_conditions_do_not_mix(field, value):
    records = [record('ep_base', 1), {**record('ep_dark', .5), field:value}]
    groups = summarize(records, {'ep_base':included('Success'), 'ep_dark':included('Failure')})['groups']
    assert len(groups) == 2
    assert all(group['difference_percentage_points'] is None for group in groups)


def test_actual_runner_maintenance_retains_conditions_and_results_route_uses_live_assessments(tmp_path, monkeypatch):
    root = runner_root(None)
    runner_type = make_runner_type(root)
    from playground import HostedRunner
    from remote_yam.run_assessments import RunAssessments
    monkeypatch.setattr(HostedRunner, 'remember_runner', lambda self, visitor: None)
    runner = runner_type.__new__(runner_type)
    runner.root, runner.robot_id, runner.secure = tmp_path, 'yam-1', False
    runner.visitors = {}
    runner.run_assessments = RunAssessments(tmp_path / 'assessments.sqlite3')
    state = {'episode_id':'ep_base', 'provider':{'provider':'dream','model':'dreamlabs/dream-1-beta',
             'image_experiment':{'brightness_factor':1}}, 'run_duration_s':120,
             'run_configuration':{'task_prompt':'Put pens in cup'}, 'run_ended_at':200.}
    visitor = SimpleNamespace(controller=SimpleNamespace(status=lambda:copy.deepcopy(state)),
                              runner_task='Put pens in cup', runner_name='Confirmed researcher')
    runner.remember_runner(visitor)
    state['episode_id'] = 'ep_dark'
    state['provider']['image_experiment']['brightness_factor'] = .5
    runner.remember_runner(visitor)
    for episode, label in [('ep_base','Success'), ('ep_dark','Failure')]:
        runner.run_assessments.register(episode, 'owner-session', ended=True)
        runner.run_assessments.assess(episode, label, 0, 'owner-session')
    messages = []
    async def send(message):
        messages.append(message)
    assert asyncio.run(runner.public_extension(
        {'method':'GET','path':'/experiment/results'}, None, send, {})) is True
    assert messages[0]['status'] == 200
    result = json.loads(messages[1]['body'])
    assert result['runs'] == 2
    assert result['groups'][0]['difference_percentage_points'] == -100
    assert 'owner-session' not in json.dumps(result)


def test_empty_data_is_not_a_performance_claim():
    assert summarize([], {})['groups'] == []
    assert summarize([record('ep_base', 1), record('ep_dark', .5)], {})['groups'][0]['difference_percentage_points'] is None


def test_fixed_experiment_ledger_survives_ephemeral_runner_root(tmp_path):
    runner_type = make_runner_type(runner_root(None), local=False)
    first, second = (runner_type.__new__(runner_type) for _ in range(2))
    first.root, second.root = tmp_path / 'old-visitor-root', tmp_path / 'new-visitor-root'
    first.experiment_root = second.experiment_root = tmp_path / 'persistent-experiment'
    expected = record('ep_saved', .5)
    ExperimentStore(first.experiment_database).remember(expected)
    assert ExperimentStore(second.experiment_database).records() == [expected]


def test_actual_connection_failure_is_separate_even_if_reviewed_as_failure():
    failure = json.loads((Path(__file__).parent / 'fixtures/connection-failure.json').read_text())
    broken = record('ep_connection', .5, interactions={'events':[failure]})
    assert broken['failure_category'] == 'model_transport'
    assert 'protocol_trace' not in json.dumps(broken)
    group = summarize([record('ep_base', 1), broken],
                      {'ep_base':included('Success'), 'ep_connection':included('Failure')})['groups'][0]
    dark = group['variants'][1]
    assert (dark['scored'], dark['failures'], dark['connection_failures']) == (0, 0, 1)
    assert dark['success_rate'] is None and group['difference_percentage_points'] is None


def test_other_errors_do_not_become_connection_failures():
    ordinary = record('ep_task', .5, error='Calibration or planning error',
                      interactions={'events':[{'kind':'model_failure','details':{'protocol_category':'other_protocol_error'}}]})
    assert ordinary.get('failure_category') is None
    group = summarize([ordinary], {'ep_task':included('Failure')})['groups'][0]
    assert group['variants'][0]['failures'] == 1


def test_terminal_configuration_and_original_revision_survive_shutdown(tmp_path):
    provider = {'provider':'dream', 'model':'dreamlabs/dream-1-beta',
                'image_experiment':{'brightness_factor':.5}}
    final = record('ep_end', .5, provider=None, last_model_command={'provider':provider},
                   run_configuration={'provider':'dream','model':provider['model'],
                                      'task_prompt':'Put pens in cup','code_revision':'runner-revision'})
    assert final['status'] == 'stopped' and final['ended_at'] == 220
    assert final['model_calls'] == 4 and final['model_s'] == 8
    store = ExperimentStore(tmp_path / 'results.sqlite3')
    store.remember({**final, 'status':'running','ended_at':None,'experiment_revision':'actual-run-source'})
    store.remember(final)
    saved = store.records()[0]
    assert saved['status'] == 'stopped' and saved['ended_at'] == 220
    assert saved['experiment_revision'] == 'actual-run-source'
    assert record('ep_other', .5, provider=None, last_model_command={'provider':provider},
                  run_configuration={'provider':'openai','model':'different'}) is None


def test_public_model_projection_matches_only_recorded_episode(tmp_path):
    runner_type = make_runner_type(runner_root(None))
    runner = runner_type.__new__(runner_type)
    runner.root, runner.secure = tmp_path, False
    ExperimentStore(tmp_path / 'brightness-experiment.sqlite3').remember(record('ep_ours', .5))
    async def response(episode):
        messages = []
        async def send(message): messages.append(message)
        await runner.json(send, 200, {'public_run':{'episode_id':episode,'model_name':'Astra'}})
        return json.loads(messages[-1]['body'])['public_run']
    ours = asyncio.run(response('ep_ours'))
    assert ours['model_name'] == 'dreamlabs/dream-1-beta'
    assert ours['image_experiment']['brightness_factor'] == .5
    assert asyncio.run(response('ep_other'))['model_name'] == 'Astra'
