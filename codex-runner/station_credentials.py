"""Private terminal-only key entry and model-only check for the Jetson station."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
DEFAULT_KEY_FILE = Path.home() / '.config/blupe-playground/openai-api-key'


class CredentialError(RuntimeError):
    pass


def valid_key(key):
    return isinstance(key, str) and 8 <= len(key) <= 4096 and all(33 <= ord(c) <= 126 for c in key)


def read_openai_key(path=DEFAULT_KEY_FILE):
    path = Path(path).expanduser()
    if path.is_symlink():
        raise CredentialError('Station key file must not be a symlink')
    try:
        metadata = path.stat()
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise CredentialError('Station key file must belong to this user and have mode 600')
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4097:
            raise CredentialError('Station key file is invalid')
        key = path.read_text().strip()
    except FileNotFoundError:
        return None
    if not valid_key(key):
        raise CredentialError('Station key file is empty or invalid')
    return key


def save_openai_key(key, path=DEFAULT_KEY_FILE):
    if not valid_key(key):
        raise CredentialError('Key must be 8–4096 characters without spaces or control characters')
    path = Path(path).expanduser()
    if path.is_symlink():
        raise CredentialError('Station key file must not be a symlink')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, temporary = tempfile.mkstemp(prefix='.openai-key-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(key + '\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def check_model(path=DEFAULT_KEY_FILE):
    from remote_yam.robocurve_policy import OpenAIAdapter
    from remote_yam.cameras import NoRedirect
    from urllib import request
    key = read_openai_key(path)
    if key is None:
        raise CredentialError('Save the key on the Jetson with blupe-playground --set-api-key first')
    adapter = OpenAIAdapter(key, 'gpt-6-astra')
    try:
        payload = {'model':'gpt-6-astra', 'input':
            'Connection check only. No robot is connected. Reply OK. Do not use tools or propose movement.',
            'tools':[], 'store':False, 'max_output_tokens':128}
        opener = request.build_opener(NoRedirect)
        adapter._urlopen = lambda req, timeout: opener.open(req, timeout=15)
        req = request.Request(adapter._endpoint, data=json.dumps(payload).encode(),
            headers={'Authorization':'Bearer '+key, 'Content-Type':'application/json'}, method='POST')
        # One bounded transport request; no retries, camera capture or controller.
        response = adapter._send_json(req)
        if not response.get('output'):
            raise RuntimeError('No model response')
        return {'ok':True, 'model':'gpt-6-astra', 'api_access_verified':True, 'physical_commands':0}
    finally:
        adapter._api_key = ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--set', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        if args.set:
            if not sys.stdin.isatty():
                raise CredentialError('Use an interactive Jetson terminal or SSH with -t for masked key entry')
            save_openai_key(getpass.getpass('OpenAI API key (hidden): ').strip())
            print('API key saved privately on this Jetson. Run blupe-playground --check-api to verify model access.')
        else:
            print(json.dumps(check_model()))
    except CredentialError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        # Provider errors can repeat account identifiers or portions of a key.
        print('Astra API check failed. Check the saved key, account access, billing, and network. No robot command was sent.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
