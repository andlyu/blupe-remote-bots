"""Read provider catalogs without starting inference or touching robot transport.

Codex: https://developers.openai.com/codex/app-server#models
Claude: Agent SDK streaming initialize response (models), using the installed CLI.
API providers: GET /v1/models. Catalog presence is not an entitlement or policy test.
"""
from contextlib import contextmanager
import json
import os
import re
import selectors
import subprocess
import tempfile
import time
from urllib import parse, request

DEFAULTS = {'openai': 'gpt-6-astra', 'codex': 'gpt-6-astra',
            'anthropic': 'claude-opus-5-5', 'claude': 'claude-opus-5-5'}
TIMEOUT = 15
MAX_BYTES = 2_000_000
EFFORTS = ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra')


def model_id(value, *, allow_empty=False):
    if not isinstance(value, str):
        raise ValueError('Invalid model name')
    value = value.strip()
    if allow_empty and not value:
        return value
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:/@+\[\]-]{0,127}', value):
        raise ValueError('Invalid model name')
    return value


def eligible_model(provider, identifier):
    """User-selected release floors, without enumerating each future release.

    Astra is the GPT-6 baseline; other GPT families begin at 6.1. Claude is
    restricted to Opus 5.5+. Explicit IDs keep older aliases from bypassing it.
    """
    if not isinstance(identifier, str):
        return False
    if provider in ('openai', 'codex'):
        match = re.fullmatch(r'gpt-(\d+)(?:\.(\d+))?((?:-[a-zA-Z0-9.]+)*)', identifier)
        if not match:
            return False
        version = (int(match[1]), int(match[2] or 0))
        suffix = match[3]
        if any(word in suffix.split('-') for word in ('audio', 'realtime', 'image', 'transcribe', 'tts')):
            return False
        return version >= (6, 1) or version == (6, 0) and bool(re.fullmatch(r'-astra(?:-\d{4}-\d{2}-\d{2})?', suffix))
    if provider in ('anthropic', 'claude'):
        match = re.fullmatch(r'claude-opus-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(?:\[1m\])?', identifier)
        return bool(match and (int(match[1]), int(match[2] or 0)) >= (5, 5))
    return False


def selected_model(provider, value):
    identifier = model_id(value, allow_empty=True) or DEFAULTS[provider]
    if not eligible_model(provider, identifier):
        raise ValueError('Choose Astra or GPT 6.1 or newer.' if provider in ('openai', 'codex')
                         else 'Choose an explicit Claude Opus 5.5 or newer model ID.')
    return identifier


def normalize(rows, provider):
    if not isinstance(rows, list):
        raise ValueError('Invalid model catalog')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('hidden') or row.get('lifecycle') == 'retired':
            continue
        modalities = row.get('inputModalities')
        capabilities = row.get('capabilities') or {}
        if (isinstance(modalities, list) and 'image' not in modalities or
                isinstance(capabilities, dict) and isinstance(capabilities.get('image_input'), dict)
                and capabilities['image_input'].get('supported') is False):
            continue
        try:
            identifier = model_id(row.get('resolvedModel') or row.get('model') or row.get('value') or row.get('id'))
        except ValueError:
            continue
        if not eligible_model(provider, identifier):
            continue
        label = row.get('displayName') or row.get('display_name') or row.get('display') or identifier
        option = {'id': identifier, 'label': str(label)[:160]}
        efforts = row.get('supportedReasoningEfforts')
        if isinstance(efforts, list):
            option['reasoning_efforts'] = [e['reasoningEffort'] for e in efforts
                if isinstance(e, dict) and e.get('reasoningEffort') in EFFORTS]
            if row.get('defaultReasoningEffort') in option['reasoning_efforts']:
                option['default_reasoning_effort'] = row['defaultReasoningEffort']
        elif isinstance(row.get('supportedEffortLevels'), list):
            option['reasoning_efforts'] = [e for e in row['supportedEffortLevels'] if e in EFFORTS]
        result[identifier] = option
    return list(result.values())


@contextmanager
def cli_channel(command, env):
    """Bounded JSONL transport; no prompts, threads, tools, or inherited runner keys."""
    with tempfile.TemporaryDirectory(prefix='blupe-model-list-') as directory:
        process = subprocess.Popen(command, cwd=directory, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                pending = b''
                total = 0
                deadline = time.monotonic() + TIMEOUT

                def send(message):
                    process.stdin.write((json.dumps(message) + '\n').encode())
                    process.stdin.flush()

                def receive():
                    nonlocal pending, total
                    while True:
                        if b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            message = json.loads(line)
                            if not isinstance(message, dict):
                                raise ValueError('Invalid catalog response')
                            return message
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(remaining):
                            raise TimeoutError('Model discovery timed out')
                        chunk = os.read(process.stdout.fileno(), 65536)
                        if not chunk:
                            raise RuntimeError('Model discovery exited')
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise ValueError('Model catalog too large')
                        pending += chunk
                yield send, receive
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
            process.stdin.close()
            process.stdout.close()


def codex_models(*, binary=None, env=None):
    from .codex_policy import codex_binary, codex_environment
    binary = binary or codex_binary()
    if not binary:
        raise RuntimeError('Codex is not installed')
    with cli_channel([binary, 'app-server', '--listen', 'stdio://'], codex_environment() if env is None else env) as (send, receive):
        sequence = 0

        def call(method, params):
            nonlocal sequence
            sequence += 1
            send({'id': sequence, 'method': method, 'params': params})
            while True:
                response = receive()
                if response.get('id') == sequence:
                    if 'error' in response or not isinstance(response.get('result'), dict):
                        raise RuntimeError('Catalog request failed')
                    return response['result']

        call('initialize', {'clientInfo': {'name': 'blupe_model_catalog', 'version': '1.0.0'}})
        send({'method': 'initialized', 'params': {}})
        rows, cursor, seen = [], None, set()
        for _ in range(20):
            page = call('model/list', {'limit': 100, 'includeHidden': False, 'cursor': cursor})
            rows.extend(page['data'])
            cursor = page.get('nextCursor')
            if not cursor:
                return normalize(rows, 'codex')
            if not isinstance(cursor, str) or cursor in seen:
                break
            seen.add(cursor)
        raise ValueError('Invalid model pagination')


def claude_models(*, binary=None, env=None):
    from .claude_policy import claude_binary, claude_environment
    binary = binary or claude_binary()
    if not binary:
        raise RuntimeError('Claude Code is not installed')
    command = [binary, '--print', '--input-format', 'stream-json', '--output-format', 'stream-json',
               '--verbose', '--no-session-persistence', '--tools', '', '--strict-mcp-config',
               '--setting-sources', '', '--settings', '{"disableAllHooks":true}']
    with cli_channel(command, claude_environment() if env is None else env) as (send, receive):
        send({'type': 'control_request', 'request_id': 'model-catalog',
              'request': {'subtype': 'initialize', 'hooks': {}, 'agents': {}, 'skills': []}})
        while True:
            message = receive()
            response = message.get('response', {})
            if message.get('type') == 'control_response' and response.get('request_id') == 'model-catalog':
                if response.get('subtype') != 'success':
                    raise RuntimeError('Catalog request failed')
                return normalize(response['response']['models'], 'claude')


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_models(provider, key):
    # Fixed origins only; never forward a browser key to a caller-supplied URL.
    endpoint = {'openai': 'https://api.openai.com/v1/models',
                'anthropic': 'https://api.anthropic.com/v1/models'}[provider]
    headers = ({'Authorization': 'Bearer ' + key} if provider == 'openai' else
               {'x-api-key': key, 'anthropic-version': '2023-06-01'})
    opener = request.build_opener(NoRedirect)
    rows, cursor, seen = [], None, set()
    deadline = time.monotonic() + TIMEOUT
    for _ in range(20):
        query = {'limit': 1000} if provider == 'anthropic' else {}
        if cursor:
            query['after_id'] = cursor
        url = endpoint + ('?' + parse.urlencode(query) if query else '')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Model discovery timed out')
        with opener.open(request.Request(url, headers=headers), timeout=remaining) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Model catalog too large')
        page = json.loads(raw)
        if not isinstance(page, dict) or not isinstance(page.get('data'), list):
            raise ValueError('Invalid model catalog')
        rows.extend(page['data'])
        if not page.get('has_more'):
            return normalize(rows, provider)
        cursor = page.get('last_id')
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            break
        seen.add(cursor)
    raise ValueError('Invalid model pagination')


def discover_models(provider, key=''):
    """Never return raw upstream errors, credentials, or CLI/account metadata."""
    if provider not in DEFAULTS:
        raise ValueError('Model discovery is unavailable for this provider')
    fallback = [{'id': DEFAULTS[provider], 'label': DEFAULTS[provider]}]
    if provider in ('openai', 'anthropic') and not key:
        return {'models': fallback, 'source': 'fallback', 'message':
                'Enter your API key to load models, or enter a model ID directly.'}
    try:
        models = (codex_models() if provider == 'codex' else claude_models() if provider == 'claude'
                  else api_models(provider, key))
        return {'models': models, 'source': 'provider', 'message':
                'Models refreshed. Choose a model with image input and tool support; account access is checked when you run.'}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError):
        return {'models': fallback, 'source': 'fallback', 'message':
                'Could not refresh models. Check your connection or CLI version, or enter a model ID directly. Your selection is unchanged.'}
