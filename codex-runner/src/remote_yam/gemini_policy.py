"""Gemini Interactions transport for the existing validated YAM policy.

Follows the stateless REST example at
https://ai.google.dev/gemini-api/docs/function-calling (2026-10-13).
Raw steps, including thought signatures, are replayed unchanged.
"""
import copy
import json
from urllib import error, request

from .robocurve_policy import RoboCurveResponsesAdapter
from .gemini_context import GeminiContext, INPUT_TOKEN_BUDGET, RETAINED_CALL_AGES, encoded

DEFAULT_MODEL = 'gemini-4-argon'
ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/interactions'


def interactions_payload(payload, thinking_level='medium'):
    history, system, calls = [], [], {}
    for item in payload['input']:
        if '_gemini_step' in item:
            step = copy.deepcopy(item['_gemini_step'])
            history.append(step)
            if step['type'] == 'function_call':
                calls[step['id']] = step['name']
        elif item.get('type') == 'function_call_output':
            identity = item['call_id']
            if identity not in calls:
                raise ValueError('Gemini tool result has no matching function call')
            history.append({'type': 'function_result', 'name': calls[identity],
                            'call_id': identity,
                            'result': [{'type': 'text', 'text': item['output']}]})
        elif item.get('role') == 'system':
            system.append(item['content'])
        elif item.get('role') == 'user':
            content = item['content']
            if isinstance(content, list):
                blocks = []
                for block in content:
                    if block['type'] == 'input_text':
                        blocks.append({'type': 'text', 'text': block['text']})
                    elif block['type'] == 'input_image':
                        prefix, data = block['image_url'].split(';base64,', 1)
                        if prefix not in {'data:image/jpeg', 'data:image/png'}:
                            raise ValueError('Gemini requires an embedded camera image')
                        blocks.append({'type': 'image', 'mime_type': prefix[5:], 'data': data,
                                       'resolution': 'high'})
                    else:
                        raise ValueError('Unsupported Gemini conversation content')
                content = blocks
            history.append({'type': 'user_input', 'content': content})
        else:
            raise ValueError('Unsupported Gemini conversation item')
    tools = [{k: copy.deepcopy(tool[k]) for k in ('type', 'name', 'description', 'parameters')}
             for tool in payload['tools']]
    # Gemini needs explicit properties for the Cartesian target map. Keep all
    # dimensions optional: unnamed dimensions hold their measured position.
    from .robocurve_trajectory import NAMES
    for tool in tools:
        if tool['name'] == 'move_to':
            targets = tool['parameters']['properties']['targets']
            targets.setdefault('properties', {name: {'type': 'number'} for name in NAMES})
            targets['additionalProperties'] = False
    return {'model': payload['model'], 'store': False, 'input': history,
            'system_instruction': '\n\n'.join(system), 'tools': tools,
            'generation_config': {'thinking_level': thinking_level, 'max_output_tokens': 32768,
                'tool_choice': {'allowed_tools': {'mode': 'any', 'tools': [t['name'] for t in tools]}}}}


def responses_output(response):
    if response.get('status') not in {'completed', 'requires_action'}:
        raise RuntimeError('Gemini response incomplete; no motion submitted')
    steps = response.get('steps')
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        raise RuntimeError('Gemini returned malformed steps')
    output = []
    for step in steps:
        kind = step.get('type')
        if kind == 'function_call':
            if (not isinstance(step.get('arguments'), dict)
                    or not isinstance(step.get('id'), str) or not step['id']
                    or not isinstance(step.get('name'), str) or not step['name']):
                raise RuntimeError('Gemini returned a malformed function call')
            item = {'type': 'function_call', 'call_id': step['id'], 'name': step['name'],
                    'arguments': json.dumps(step['arguments'], allow_nan=False)}
        elif kind == 'model_output':
            content = step.get('content')
            if not isinstance(content, list) or any(
                    not isinstance(b, dict) or b.get('type') != 'text'
                    or not isinstance(b.get('text'), str) for b in content):
                raise RuntimeError('Gemini returned unsupported model output')
            item = {'type': 'message', 'role': 'assistant',
                    'content': [{'type': 'output_text', 'text': b['text']} for b in content]}
        elif kind == 'thought':
            # Opaque native state is retained for Gemini, never treated as an action.
            item = {'type': 'reasoning', 'summary': []}
        else:
            raise RuntimeError('Gemini returned unsupported step type')
        item['_gemini_step'] = copy.deepcopy(step)
        output.append(item)
    return {'output': output, 'usage': response.get('usage', {})}


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GeminiAdapter(RoboCurveResponsesAdapter):
    provider_name = 'gemini'

    def __init__(self, api_key, model=DEFAULT_MODEL, *, thinking_level='medium', calling_mode='sparse', timeout_s=900, **kwargs):
        if thinking_level not in {'low', 'medium', 'high'}:
            raise ValueError('Gemini thinking level must be low, medium or high')
        super().__init__(api_key, model, ENDPOINT, **kwargs)
        self.reasoning_effort = thinking_level
        self.timeout_s = timeout_s
        self._urlopen = request.build_opener(NoRedirect).open
        self._context = GeminiContext()
        self.set_calling_mode(calling_mode)

    def set_calling_mode(self, mode):
        if mode not in ('sparse', 'normal'):
            raise ValueError('Choose Sparse calling or Normal calling')
        if self._calls or self._history:
            raise ValueError('Choose the Gemini calling mode before starting a run')
        self.calling_mode = mode
        if self._recorder:
            path = self._recorder.path / 'gemini-config.json'
            path.write_text(json.dumps({'model': self.model, 'calling_mode': mode,
                'thinking_level': self.reasoning_effort,
                'retained_call_ages': list(RETAINED_CALL_AGES) if mode == 'sparse' else None,
                'input_token_budget_estimate': INPUT_TOKEN_BUDGET if mode == 'sparse' else None}) + '\n')
            path.chmod(0o600)

    def public_config(self):
        return {**super().public_config(), 'display_name': 'Gemini 4 Argon' if self.model == DEFAULT_MODEL else self.model,
                'calling_mode': self.calling_mode,
                'context': {'input_token_budget_estimate': INPUT_TOKEN_BUDGET if self.calling_mode == 'sparse' else None,
                            'retained_call_ages': list(RETAINED_CALL_AGES) if self.calling_mode == 'sparse' else None,
                            'estimated_input_tokens': self._context.last_estimate if self.calling_mode == 'sparse' else None,
                            'selected_calls': list(self._context.selected_calls) if self.calling_mode == 'sparse' else None}}

    def _post_json(self, payload):
        if self.cancelled():
            raise RuntimeError('Model request cancelled')
        if self._pending is not None:
            raise RuntimeError('Gemini cannot infer while motion is pending')
        wire = (self._context.prepare(payload,
            lambda p: interactions_payload(p, self.reasoning_effort), pending=self._pending is not None)
            if self.calling_mode == 'sparse' else interactions_payload(payload, self.reasoning_effort))
        # Base recorder retains the complete transcript; this records actual input.
        self._record('gemini_request', call=self._calls, request=wire,
                     calling_mode=self.calling_mode,
                     estimated_input_tokens=self._context.last_estimate if self.calling_mode == 'sparse' else None,
                     selected_calls=self._context.selected_calls if self.calling_mode == 'sparse' else None)
        req = request.Request(ENDPOINT, data=encoded(wire),
            headers={'x-goog-api-key': self._api_key, 'Content-Type': 'application/json'}, method='POST')
        # No automatic retries: a timed-out inference may still be running.
        try:
            with self._urlopen(req, timeout=self.timeout_s) as response:
                raw = json.loads(response.read())
        except error.HTTPError as exc:
            status = exc.code
            exc.close()
            # Provider error bodies can echo keys or input; retain only status.
            raise RuntimeError(f'Gemini inference failed: HTTP {status}') from None
        except (error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise RuntimeError(f'Gemini inference connection failed: {type(exc).__name__}') from None
        if self.cancelled():
            raise RuntimeError('Model request cancelled')
        if not isinstance(raw, dict):
            raise RuntimeError('Gemini returned a non-object response')
        return responses_output(raw)
