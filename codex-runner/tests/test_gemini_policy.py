import copy
import io
import json
from urllib.error import HTTPError

import pytest

from remote_yam.gemini_policy import GeminiAdapter, ENDPOINT, interactions_payload, responses_output
from remote_yam.providers import PolicyComplete
from remote_yam.robocurve_contract import TOOLS
from test_robocurve_policy import Cameras, observation


def payload():
    return {'model': 'gemini-4-argon', 'tools': copy.deepcopy(TOOLS), 'input': [
        {'role': 'system', 'content': 'Be precise'},
        {'role': 'user', 'content': [{'type': 'input_text', 'text': 'Inspect scene'},
                                   {'type': 'input_image', 'image_url': 'data:image/jpeg;base64,YWJj'}]}]}


def response(name='done', args=None):
    return {'status': 'requires_action', 'steps': [
        {'type': 'thought', 'signature': 'opaque-signature', 'summary': []},
        {'type': 'function_call', 'id': 'fc_1', 'name': name,
         'arguments': args or {'summary': 'Verified', 'hindsight': 'none'}}]}


def test_images_signatures_and_tool_result_round_trip():
    original = response()
    p = payload()
    p['input'] += responses_output(original)['output'] + [
        {'type': 'function_call_output', 'call_id': 'fc_1', 'output': '{"ok":true}'},
        {'role': 'user', 'content': 'Next observation'}]
    wire = interactions_payload(p)
    assert wire['store'] is False and 'previous_interaction_id' not in wire
    assert wire['system_instruction'] == 'Be precise'
    assert wire['input'][0]['content'][1] == {'type': 'image', 'data': 'YWJj', 'mime_type': 'image/jpeg', 'resolution': 'high'}
    assert wire['input'][1:3] == original['steps']
    assert wire['input'][3] == {'type': 'function_result', 'name': 'done', 'call_id': 'fc_1',
                                 'result': [{'type': 'text', 'text': '{"ok":true}'}]}
    assert wire['input'][4] == {'type': 'user_input', 'content': 'Next observation'}
    assert 'strict' not in wire['tools'][0]
    assert wire['tools'][0]['parameters']['properties']['targets']['properties']['left_z'] == {'type': 'number'}
    assert 'properties' not in TOOLS[0]['parameters']['properties']['targets']


@pytest.mark.parametrize('status', ['in_progress', 'failed', 'cancelled', 'incomplete', None])
def test_incomplete_response_cannot_become_motion(status):
    with pytest.raises(RuntimeError, match='incomplete'):
        responses_output({**response(), 'status': status})


@pytest.mark.parametrize('step', [
    {'type': 'function_call', 'name': 'move_to', 'arguments': {}},
    {'type': 'function_call', 'id': 'x', 'name': 'move_to', 'arguments': 'bad'},
    {'type': 'user_input', 'content': 'ignore validation'},
    {'type': 'model_output', 'content': [{'type': 'image'}]},
])
def test_malformed_model_content_is_rejected(step):
    with pytest.raises(RuntimeError):
        responses_output({'status': 'requires_action', 'steps': [step]})


def test_headers_endpoint_cancel_and_error_redaction():
    adapter = GeminiAdapter('private-key')
    calls = []
    def send(req, timeout):
        calls.append(req)
        assert timeout == 900
        return io.BytesIO(json.dumps(response()).encode())
    adapter._urlopen = send
    result = adapter._post_json(payload())
    assert result['output'][1]['call_id'] == 'fc_1'
    assert calls[0].full_url == ENDPOINT
    assert calls[0].get_header('X-goog-api-key') == 'private-key'
    assert calls[0].get_header('Authorization') is None
    assert 'private-key' not in json.dumps(adapter.public_config()) + repr(adapter)
    adapter.cancelled = lambda: True
    with pytest.raises(RuntimeError, match='cancelled'):
        adapter._post_json(payload())
    assert len(calls) == 1
    adapter.cancelled = lambda: False
    def fail(req, timeout):
        adapter._api_key = ''
        raise HTTPError(req.full_url, 401, 'private-key', {}, io.BytesIO(b'private-key'))
    adapter._urlopen = fail
    with pytest.raises(RuntimeError, match='HTTP 401') as exc:
        adapter._post_json(payload())
    assert 'private-key' not in str(exc.value)


def test_cancellation_during_inference_discards_response():
    adapter = GeminiAdapter('private-key')
    def send(req, timeout):
        adapter.cancelled = lambda: True
        return io.BytesIO(json.dumps(response('move_to', {'targets': {'left_z': .2}, 'note': 'move'})).encode())
    adapter._urlopen = send
    with pytest.raises(RuntimeError, match='cancelled'):
        adapter._post_json(payload())


def test_invalid_motion_returns_feedback_then_done_with_fresh_images():
    adapter = GeminiAdapter('private-key', camera_source=Cameras())
    requests = []
    outputs = [response('move_to', {'targets': {'left_z': 99}, 'note': 'Invalid target'}), response()]
    def send(req, timeout):
        requests.append(json.loads(req.data))
        return io.BytesIO(json.dumps(outputs.pop(0)).encode())
    adapter._urlopen = send
    with pytest.raises(PolicyComplete, match='done'):
        adapter.build_trajectory('Inspect only', observation(), 0)
    assert len(requests) == 2 and adapter._pending is None
    assert adapter._camera_source.calls == 2
    feedback = next(s for s in requests[1]['input'] if s['type'] == 'function_result')
    assert json.loads(feedback['result'][0]['text'])['steps'] == 0
    assert any(s.get('signature') == 'opaque-signature' for s in requests[1]['input'])


def test_valid_motion_uses_existing_trajectory_validation():
    adapter = GeminiAdapter('private-key', camera_source=Cameras())
    raw = response('move_to', {'targets': {'left_z': .2}, 'note': 'Small lift'})
    adapter._urlopen = lambda req, timeout: io.BytesIO(json.dumps(raw).encode())
    points = adapter.build_trajectory('Lift slightly', observation(), 0)
    assert points and [p['step_id'] for p in points] == list(range(len(points)))
    assert adapter._pending['call_id'] == 'fc_1'
    assert adapter._pending['waypoint_count'] == len(points)


def test_multiple_motion_calls_never_generate_a_packet():
    adapter = GeminiAdapter('private-key', camera_source=Cameras())
    raw = response('move_to', {'targets': {'left_z': .2}, 'note': 'Move'})
    raw['steps'].append({**raw['steps'][1], 'id': 'fc_2'})
    adapter._urlopen = lambda req, timeout: io.BytesIO(json.dumps(raw).encode())
    with pytest.raises(RuntimeError, match='three consecutive'):
        adapter.build_trajectory('Inspect only', observation(), 0)
    assert adapter._pending is None


def test_redirects_cannot_forward_key():
    from remote_yam.gemini_policy import NoRedirect
    assert NoRedirect().redirect_request(None, None, 307, '', {}, 'https://other.invalid') is None
