import io
import json
from unittest.mock import patch
from urllib.error import HTTPError
import pytest
from remote_yam.anthropic_policy import AnthropicAdapter, messages_payload, responses_output


def payload():
    return {'model':'claude-opus-5-5','tools':[{'name':'done','description':'Finish','parameters':{'type':'object'}}],
            'input':[{'role':'system','content':'Be precise'}, {'role':'user','content':[
                {'type':'input_text','text':'Move block'},
                {'type':'input_image','image_url':'data:image/jpeg;base64,YWJj'}]}]}


def test_images_and_tool_feedback_round_trip():
    p=payload()
    raw={'stop_reason':'tool_use','content':[{'type':'text','text':'Done'},
          {'type':'tool_use','id':'toolu_1','name':'done','input':{'summary':'Done','hindsight':'OK'}}]}
    p['input'] += responses_output(raw)['output'] + [
        {'type':'function_call_output','call_id':'toolu_1','output':'{"ok":true}'},
        {'role':'user','content':[{'type':'input_text','text':'Next observation'}]}]
    wire=messages_payload(p)
    assert wire['system']=='Be precise'
    assert [m['role'] for m in wire['messages']]==['user','assistant','user']
    assert wire['messages'][0]['content'][1]['source']=={'type':'base64','media_type':'image/jpeg','data':'YWJj'}
    assert wire['messages'][1]['content'][1]['id']=='toolu_1'
    assert wire['messages'][2]['content'][0]['tool_use_id']=='toolu_1'
    assert wire['messages'][2]['content'][1]['text']=='Next observation'
    assert wire['tool_choice']['disable_parallel_tool_use'] is True
    assert wire['tools'][0]['input_schema']=={'type':'object'}


@pytest.mark.parametrize('reason',['max_tokens','refusal','pause_turn',None])
def test_incomplete_responses_never_become_motion(reason):
    with pytest.raises(RuntimeError,match='incomplete'):
        responses_output({'stop_reason':reason,'content':[{'type':'tool_use','id':'x','name':'move_to','input':{}}]})


def test_fixed_endpoint_headers_and_response_conversion():
    adapter=AnthropicAdapter('private-key')
    calls=[]
    def send(req):
        calls.append(req)
        return io.BytesIO(json.dumps({'stop_reason':'tool_use','content':[
            {'type':'tool_use','id':'toolu_1','name':'done','input':{'summary':'OK','hindsight':'OK'}}]}).encode())
    adapter._urlopen=lambda req,timeout: send(req)
    result=adapter._post_json(payload())
    req=calls[0]
    assert req.full_url=='https://api.anthropic.com/v1/messages'
    assert req.get_header('Anthropic-version')=='2023-06-01'
    assert req.get_header('Authorization')=='Bearer private-key'
    assert result['output'][0]['call_id']=='toolu_1'
    assert 'private-key' not in repr(adapter)
    adapter.cancelled=lambda:True
    with pytest.raises(RuntimeError,match='cancelled'): adapter._post_json(payload())
    assert len(calls)==1


def test_failed_request_redacts_key_after_revocation():
    adapter=AnthropicAdapter('private-key')
    def send(req,timeout):
        adapter._api_key=''
        raise HTTPError(req.full_url,401,'Unauthorized',{},io.BytesIO(b'{"error":{"message":"bad private-key"}}'))
    adapter._urlopen=send
    with pytest.raises(RuntimeError) as exc: adapter._post_json(payload())
    assert 'private-key' not in str(exc.value)
    assert '[REDACTED]' in str(exc.value)


def test_fable_preserves_signed_turn_across_tool_feedback_without_logging_thinking():
    model = 'claude-fable-5-2'
    p = {**payload(), 'model': model}
    adapter = AnthropicAdapter('private-key', model)
    turns = [
        {'type':'thinking','thinking':'','signature':'first-signature'},
        {'type':'text','text':'Checking the scene'},
        {'type':'redacted_thinking','data':'private-signature'},
        {'type':'tool_use','id':'toolu_1','name':'move_to','input':{'targets':{'left_x':0.4},'note':'Move'}},
    ]
    responses = iter([
        {'model':model,'stop_reason':'tool_use','content':turns},
        {'model':model,'stop_reason':'tool_use','content':[
            {'type':'tool_use','id':'toolu_2','name':'done','input':{'summary':'OK','hindsight':'OK'}}]},
    ])
    requests = []
    def send(req, timeout):
        requests.append(json.loads(req.data))
        return io.BytesIO(json.dumps(next(responses)).encode())
    adapter._urlopen = send
    first = adapter._post_json(p)
    assert first['model'] == model
    assert 'private-signature' not in json.dumps(first)
    p['input'] += first['output'] + [
        {'type':'function_call_output','call_id':'toolu_1','output':'{"ok":true}'},
        {'role':'user','content':'New measured observation'},
    ]
    assert adapter._post_json(p)['output'][0]['name'] == 'done'
    assert requests[0]['tool_choice'] == {'type':'auto','disable_parallel_tool_use':True}
    assert requests[1]['messages'][:1] == requests[0]['messages']
    assert requests[1]['messages'][1] == {'role':'assistant','content':turns}
    assert requests[1]['messages'][2]['content'][0]['tool_use_id'] == 'toolu_1'


@pytest.mark.parametrize('returned_model', ['claude-opus-5', None])
def test_fable_api_never_returns_motion_on_fallback_or_missing_model(returned_model):
    model = 'claude-fable-5-2'
    adapter = AnthropicAdapter('private-key', model)
    body = {'model':returned_model,'stop_reason':'tool_use','content':[
        {'type':'tool_use','id':'toolu_1','name':'move_to','input':{'targets':{'left_x':0.4},'note':'Move'}}]}
    adapter._urlopen = lambda req, timeout: io.BytesIO(json.dumps(body).encode())
    with pytest.raises(RuntimeError, match='did not confirm Fable 5.2'):
        adapter._post_json({**payload(), 'model':model})
    assert adapter.public_config()['resolved_model'] is None
