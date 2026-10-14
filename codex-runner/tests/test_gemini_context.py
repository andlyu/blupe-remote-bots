import copy
import io
import json

import pytest

from remote_yam.gemini_context import GeminiContext, RETAINED_CALL_AGES, select_history
from remote_yam.gemini_policy import GeminiAdapter, interactions_payload, responses_output
from test_gemini_policy import response


def view(number):
    content = [{'type':'input_text', 'text':f'observation {number}'}]
    for camera in ('top','left','right'):
        content.extend([{'type':'input_text', 'text':camera},
                        {'type':'input_image', 'image_url':f'data:image/jpeg;base64,YWJj'}])
    return {'role':'user','content':content}


def transcript(count):
    history = [{'role':'system','content':'Safety instructions'}, {'role':'user','content':'Goal: move once'}]
    for number in range(1, count+1):
        history.append(view(number))
        if number == 4:
            history.append({'role':'system','content':'Newer steering supersedes the original task'})
            history.append({'role':'user','content':'Run-owner steering update #1:\nUse the left arm only'})
        raw = response('move_to', {'targets': {'left_z': .2}, 'note': f'move {number}'})
        raw['steps'][0]['signature'] = f'exact-signature-{number}'
        raw['steps'][1]['id'] = f'call-{number}'
        history.extend(responses_output(raw)['output'])
        history.append({'type':'function_call_output','call_id':f'call-{number}',
                        'output':json.dumps({'ok':number % 2 == 0, 'steps':number})})
    history.append(view(count+1))
    return history


def payload(history):
    return {'model':'gemini-4-argon','input':history,'tools':[]}


def test_sparse_pattern_is_relative_chronological_and_retains_every_camera():
    history = transcript(12)
    original = copy.deepcopy(history)
    selected, numbers = select_history(history)
    assert numbers == [3, 6, 8, 10, 11, 12]
    wire = interactions_payload(payload(selected))
    assert [s['id'] for s in wire['input'] if s['type'] == 'function_call'] == [f'call-{n}' for n in numbers]
    assert [s['call_id'] for s in wire['input'] if s['type'] == 'function_result'] == [f'call-{n}' for n in numbers]
    assert sum(len(s['content']) == 7 for s in wire['input'] if isinstance(s.get('content'),list)) == 7
    for number in numbers:
        native = [i['_gemini_step'] for i in history if '_gemini_step' in i and
                  (i['_gemini_step'].get('id') == f'call-{number}' or i['_gemini_step'].get('signature') == f'exact-signature-{number}')]
        assert all(item in wire['input'] for item in native)
    assert 'Use the left arm only' in json.dumps(wire)
    assert 'Safety instructions' in wire['system_instruction']
    assert 'Newer steering' in wire['system_instruction']
    assert 'Goal: move once' in json.dumps(wire)
    assert 'observation 13' in json.dumps(wire)
    assert history == original


def test_omitted_calls_reenter_from_full_history_and_then_age_out():
    for count in range(1, 26):
        selected, numbers = select_history(transcript(count))
        assert numbers == sorted(count-age+1 for age in RETAINED_CALL_AGES if age <= count)
    # Call 4 is age four at call 7, then age five at call 8.
    assert 4 not in select_history(transcript(7))[1]
    assert 4 in select_history(transcript(8))[1]
    assert 4 not in select_history(transcript(14))[1]


def test_unresolved_exchange_is_not_dropped_even_when_its_age_would_be_omitted():
    history = transcript(7)
    history = [i for i in history if not (i.get('type') == 'function_call_output' and i['call_id'] == 'call-4')]
    with pytest.raises(RuntimeError, match='unresolved'):
        select_history(history)
    with pytest.raises(RuntimeError, match='pending'):
        GeminiContext().prepare(payload(transcript(1)), interactions_payload, pending=True)


def test_oversized_selected_input_fails_without_summarizing_or_mutating():
    history = transcript(10)
    history[0]['content'] = '安全' * 40000
    before = copy.deepcopy(history)
    with pytest.raises(RuntimeError, match='context budget'):
        GeminiContext().prepare(payload(history), interactions_payload)
    assert history == before


def test_sparse_default_normal_full_history_and_recorded_mode(tmp_path):
    history = transcript(12)
    for mode in ('sparse', 'normal'):
        adapter = GeminiAdapter('test-key', calling_mode=mode, recording_root=tmp_path)
        requests = []
        def send(req, timeout):
            requests.append(json.loads(req.data))
            return io.BytesIO(json.dumps(response()).encode())
        adapter._urlopen = send
        adapter._history = copy.deepcopy(history)
        adapter._record('request', request=payload(history))
        adapter._post_json(payload(history))
        count = sum(s['type'] == 'function_call' for s in requests[0]['input'])
        assert count == (6 if mode == 'sparse' else 12)
        assert adapter._history == history
        assert adapter.public_config()['calling_mode'] == mode
        rows = [json.loads(line) for line in (adapter._recorder.path/'calls.jsonl').read_text().splitlines()]
        assert len(rows[0]['request']['input']) == len(history)
        assert rows[1]['kind'] == 'gemini_request' and rows[1]['calling_mode'] == mode
        assert sum(s['type'] == 'function_call' for s in rows[1]['request']['input']) == count
    assert GeminiAdapter('test-key').calling_mode == 'sparse'


def test_new_instance_is_fresh_and_mode_cannot_change_during_a_run():
    adapter = GeminiAdapter('test-key')
    adapter._context.prepare(payload(transcript(11)), interactions_payload)
    fresh = GeminiAdapter('test-key')
    assert fresh._history == [] and fresh._context.selected_calls == []
    adapter._calls = 1
    with pytest.raises(ValueError, match='before starting'):
        adapter.set_calling_mode('normal')
    for mode in ('', 'checkpoint', None, [], 1):
        with pytest.raises(ValueError, match='Choose'):
            GeminiAdapter('test-key', calling_mode=mode)
