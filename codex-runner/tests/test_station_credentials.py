import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from station_credentials import CredentialError, read_openai_key, save_openai_key, check_model


class CredentialTests(unittest.TestCase):
    def test_atomic_private_save_replaces_only_requested_key_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'private/key'
            self.assertIsNone(read_openai_key(path))
            save_openai_key('fixture-private-key',path)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
            self.assertEqual(read_openai_key(path),'fixture-private-key')
            save_openai_key('replacement-fixture-key',path)
            self.assertEqual(read_openai_key(path),'replacement-fixture-key')
            path.chmod(0o644)
            with self.assertRaises(CredentialError):read_openai_key(path)

    def test_symlinks_and_control_characters_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'other';target.write_text('fixture-key')
            path=Path(directory)/'key';path.symlink_to(target)
            with self.assertRaises(CredentialError):save_openai_key('replacement-key',path)
            with self.assertRaises(CredentialError):read_openai_key(path)
            self.assertEqual(target.read_text(),'fixture-key')
            for value in ('short','fixture key','fixture\nkey'):
                with self.assertRaises(CredentialError):save_openai_key(value,target)

    def test_connection_probe_is_text_only_single_transport_and_never_dispatches(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'key';save_openai_key('fixture-private-key',path)
            with patch('remote_yam.robocurve_policy.OpenAIAdapter._send_json',return_value={'output':[{'type':'message'}]}) as send, \
                    patch('remote_yam.session.HttpSessionAPI.create_session') as create:
                result=check_model(path)
            self.assertTrue(result['ok']);self.assertEqual(result['physical_commands'],0)
            create.assert_not_called();send.assert_called_once()
            request=send.call_args.args[0];payload=json.loads(request.data)
            self.assertEqual(payload['tools'],[])
            self.assertIsInstance(payload['input'],str)
            self.assertNotIn('fixture-private-key',json.dumps(result))


if __name__=='__main__':unittest.main()
