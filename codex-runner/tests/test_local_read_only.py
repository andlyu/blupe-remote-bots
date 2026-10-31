import shutil
import unittest
from unittest.mock import AsyncMock, patch

from local_playground import LocalPlayground, PUBLIC_SESSION_API
from playground import RequestError
from remote_yam.session import MockSessionAPI


class LocalReadOnlyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = LocalPlayground(public_origin='http://127.0.0.1:8791',
            session_api=PUBLIC_SESSION_API, camera_origin='http://127.0.0.1:8089',
            hardware_control=False, development=True, api_factory=MockSessionAPI)
        self.addCleanup(shutil.rmtree, self.app.root, True)

    async def test_public_session_announces_read_only_and_resets_it_when_enabled(self):
        with patch('playground.HostedRunner.session_extension', new_callable=AsyncMock,
                   return_value=({'existing':'value'}, [])):
            setup, _ = await self.app.session_extension({}, None)
            self.assertTrue(setup['read_only'])
            self.assertEqual(setup['existing'], 'value')
            self.app.hardware_control = True
            setup, _ = await self.app.session_extension({}, None)
            self.assertFalse(setup['read_only'])

    def test_read_only_rejects_before_provider_setup_or_queue_admission(self):
        with patch('playground.HostedRunner.launch') as launch:
            with self.assertRaisesRegex(RequestError, 'Read-only local preview'):
                self.app.launch(None, {'prompt':'put ducky onto plate'})
            launch.assert_not_called()
        self.assertFalse(self.app.visitors)

    def test_normal_control_enabled_launch_retains_existing_path(self):
        self.app.hardware_control = True
        with patch('playground.HostedRunner.launch', return_value={'status':'queued'}) as launch:
            result = self.app.launch(None, {'prompt':'test'})
        self.assertEqual(result, {'status':'queued'})
        launch.assert_called_once()
