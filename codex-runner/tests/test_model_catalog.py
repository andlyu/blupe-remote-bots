import io
import json
import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from remote_yam import model_catalog as catalog


class ModelCatalogTests(unittest.TestCase):
    def test_release_floors_include_future_models_without_a_release_allowlist(self):
        for provider in ('openai', 'codex'):
            for model in ('gpt-6-astra', 'gpt-6-astra-2026-01-01', 'gpt-6.1-sol',
                          'gpt-6.12-sol', 'gpt-7-sol', 'gpt-7-new-family'):
                self.assertEqual(catalog.selected_model(provider, ' ' + model + ' '), model)
            for model in ('gpt-4.1', 'gpt-5.6-sol', 'gpt-6-sol', 'gpt-6-astra-fake',
                          'gpt-6.1-image', 'latest', 'claude-opus-6', 'gpt-6.1-sol\n--help'):
                with self.assertRaises(ValueError, msg=model):
                    catalog.selected_model(provider, model)
        for provider in ('anthropic', 'claude'):
            for model in ('claude-opus-5-5', 'claude-opus-5-5[1m]', 'claude-opus-5-12',
                          'claude-opus-6', 'claude-opus-6-20270101'):
                self.assertEqual(catalog.selected_model(provider, model), model)
            for model in ('opus', 'default', 'claude-opus-5-4', 'claude-opus-5-20261011',
                          'claude-sonnet-6', 'claude-haiku-6', 'claude-fable-6'):
                with self.assertRaises(ValueError, msg=model):
                    catalog.selected_model(provider, model)

    def test_catalog_filters_capabilities_and_resolves_claude_aliases(self):
        rows = [{'id':'gpt-6.1-sol','displayName':'Sol', 'inputModalities':['text','image'],
                 'supportedReasoningEfforts':[{'reasoningEffort':'high'}], 'defaultReasoningEffort':'high'},
                {'id':'gpt-7-sol','inputModalities':['text']}, {'id':'gpt-8-sol','hidden':True},
                {'id':'gpt-9-sol','lifecycle':'retired'}, {'id':'gpt-6-sol'}, {'id':'invalid name'}]
        self.assertEqual(catalog.normalize(rows, 'codex'), [{'id':'gpt-6.1-sol','label':'Sol',
            'reasoning_efforts':['high'],'default_reasoning_effort':'high'}])
        self.assertEqual(catalog.normalize([{'value':'opus', 'resolvedModel':'claude-opus-6',
            'displayName':'Opus', 'supportedEffortLevels':['low','max']}], 'claude'),
            [{'id':'claude-opus-6','label':'Opus','reasoning_efforts':['low','max']}])
        self.assertEqual(catalog.normalize([{'id':'claude-opus-6',
            'capabilities':{'image_input':{'supported':False}}}], 'anthropic'), [])

    def test_codex_catalog_pages_use_only_initialize_and_list_no_inference(self):
        sent = []
        responses = iter([{'id':1,'result':{}}, {'method':'notice'},
            {'id':2,'result':{'data':[{'model':'gpt-6-astra'}],'nextCursor':'page-two'}},
            {'id':3,'result':{'data':[{'model':'gpt-6.1-sol'}],'nextCursor':None}}])
        @contextmanager
        def channel(command, env):
            self.assertIn('app-server', command)
            self.assertNotIn('OPENAI_API_KEY', env)
            yield sent.append, lambda: next(responses)
        with patch('remote_yam.codex_policy.codex_binary', return_value='codex'), \
             patch.dict(os.environ, {'OPENAI_API_KEY':'never-inherit'}), \
             patch.object(catalog, 'cli_channel', channel):
            self.assertEqual([x['id'] for x in catalog.codex_models()], ['gpt-6-astra','gpt-6.1-sol'])
        self.assertEqual([x['method'] for x in sent], ['initialize','initialized','model/list','model/list'])
        self.assertEqual(sent[-1]['params']['cursor'], 'page-two')

    def test_claude_catalog_sends_no_user_prompt_and_does_not_inherit_api_keys(self):
        sent = []
        @contextmanager
        def channel(command, env):
            self.assertNotIn('ANTHROPIC_API_KEY', env)
            self.assertIn('--no-session-persistence', command)
            yield sent.append, lambda: {'type':'control_response','response':{'subtype':'success',
                'request_id':'model-catalog','response':{'models':[{'value':'opus', 'resolvedModel':'claude-opus-6'}]}}}
        with patch('remote_yam.claude_policy.claude_binary', return_value='claude'), \
             patch.dict(os.environ, {'ANTHROPIC_API_KEY':'never-inherit'}), \
             patch.object(catalog, 'cli_channel', channel):
            self.assertEqual(catalog.claude_models()[0]['id'], 'claude-opus-6')
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['request']['subtype'], 'initialize')

    def test_api_pagination_and_credential_scope(self):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(json.dumps(page).encode()) for page in [
            {'data':[{'id':'claude-opus-5-5'}],'has_more':True,'last_id':'claude-opus-5-5'},
            {'data':[{'id':'claude-opus-6'}],'has_more':False}]]
        with patch.object(catalog.request, 'build_opener', return_value=opener):
            result = catalog.api_models('anthropic', 'private-key')
        self.assertEqual([row['id'] for row in result], ['claude-opus-5-5','claude-opus-6'])
        requests = [call.args[0] for call in opener.open.call_args_list]
        self.assertIn('after_id=claude-opus-5-5', requests[1].full_url)
        self.assertEqual(requests[0].get_header('X-api-key'), 'private-key')
        self.assertNotIn('private-key', json.dumps(result))
        self.assertIsNone(catalog.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))

    def test_failure_is_sanitized_and_no_key_does_not_make_network_request(self):
        with patch.object(catalog, 'api_models', side_effect=OSError('secret-account-key')) as fetch:
            self.assertEqual(catalog.discover_models('openai')['source'], 'fallback')
            fetch.assert_not_called()
            result = catalog.discover_models('openai','secret-account-key')
        self.assertEqual(result['source'], 'fallback')
        self.assertNotIn('secret-account-key', json.dumps(result))

    def test_cli_transport_handles_multiple_frames_and_bounds_wait(self):
        script = 'import sys,time; input(); print(\'{"id":1}\\n{"id":2}\',flush=True); time.sleep(10)'
        with catalog.cli_channel([sys.executable,'-c',script], os.environ.copy()) as (send,receive):
            send({'hello':True})
            self.assertEqual(receive(), {'id':1})
            self.assertEqual(receive(), {'id':2})
        with patch.object(catalog, 'TIMEOUT', .05):
            with catalog.cli_channel([sys.executable,'-c','import time; time.sleep(10)'], os.environ.copy()) as (_, receive):
                with self.assertRaises(TimeoutError):
                    receive()


if __name__ == '__main__':
    unittest.main()
