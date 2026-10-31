"""RunPod LB readiness parent; private authenticated endpoint, local model child.

RunPod HTTP lifecycle: /ping204 preparing,200 after real CUDA warmup,503 failed.
Runtime preparation happens on a separate CPU Pod local SSD, never on NFS.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REVISION = '8dcbed66f2380e4393189c303ea72488eb9e63c2'
BASE_IMAGE = 'pytorch/pytorch@sha256:cf5aa3f7045a68c10d80f546746591c5ccae6a33729e5e32625ff76bd2c036fe'
ROOT = Path('/runpod-volume')
APP = Path('/tmp/molmoact2-app')
started = time.monotonic()
phase = 'starting'
failed = False
child = None


def step(name):
    global phase
    phase = name
    print(json.dumps(dict(event='bootstrap_phase', phase=name,
                          elapsed_seconds=time.monotonic() - started)), flush=True)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def prepare():
    global child, failed
    try:
        if not ROOT.is_dir() or not os.path.ismount(ROOT):
            raise RuntimeError('Expected persistent RunPod network volume')
        subprocess.run(['nvidia-smi'], check=True)  # Inventory devices/processes first.
        bundle = json.loads((APP / 'bundle.json').read_text())
        for name in ('worker.py', 'protocol.py', 'guidance.py'):
            (APP / name).write_text(bundle[name])
        receipt = json.loads((ROOT / 'molmoact2-runtime-local.json').read_text())
        expected = hashlib.sha256(bundle['requirements.txt'].encode()).hexdigest()
        if (receipt.get('model_revision') != REVISION or receipt.get('base_image') != BASE_IMAGE
                or receipt.get('requirements_sha256') != expected):
            raise RuntimeError('Prepared runtime identity mismatch')
        archive = ROOT / 'molmoact2-runtime-local.tar.gz'
        step('verify_and_extract_prepared_runtime')
        if archive.stat().st_size != receipt['bytes'] or sha256(archive) != receipt['sha256']:
            raise RuntimeError('Prepared runtime checksum mismatch')
        subprocess.run(['tar', '-C', '/opt', '-xzf', str(archive)], check=True)
        model_root = ROOT / 'molmoact2-yam'
        checkpoint = json.loads((model_root / 'identity.json').read_text())
        if checkpoint.get('revision') != REVISION or checkpoint.get('model') != 'allenai/MolmoAct2-BimanualYAM':
            raise RuntimeError('Prepared checkpoint identity mismatch')
        # Every asset was verified against HF LFS SHA256 or its Git blob at
        # preparation. Recheck all executable/config/tokenizer files now;
        # large weights are read by safetensors without another full hash pass.
        for item in checkpoint['files']:
            path = model_root / item['path']
            if path.stat().st_size != item['bytes']:
                raise RuntimeError('Checkpoint asset size changed')
            if path.suffix != '.safetensors' and sha256(path) != item['sha256']:
                raise RuntimeError('Checkpoint code/config checksum changed')
        step('model_load_and_real_warmup')
        env = dict(os.environ, TOKENIZERS_PARALLELISM='false', HF_HUB_OFFLINE='1',
                   TRANSFORMERS_OFFLINE='1', HF_MODULES_CACHE='/opt/molmoact2-modules')
        child = subprocess.Popen(['/opt/molmoact2-runtime/bin/python', '-u', str(APP / 'worker.py')], env=env)
        child.wait()
        raise RuntimeError('MolmoAct2 model process exited')
    except Exception:
        import traceback
        traceback.print_exc()
        failed = True
        step('failed')


def upstream(path, data=None):
    request = Request('http://127.0.0.1:8202' + path, data=data,
                      headers={'Content-Type': 'application/json'})
    try:
        with urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path not in ('/ping', '/health'):
            return self.reply(404, b'{}')
        try:
            code, data = upstream('/health')
            value = json.loads(data)
            if self.path == '/ping':
                return self.reply(200 if code == 200 else 503 if value.get('failed') else 204, b'')
            value.update(bootstrap_phase=phase, bootstrap_seconds=time.monotonic() - started)
            return self.reply(code, json.dumps(value).encode())
        except OSError:
            code = 503 if failed else 204 if self.path == '/ping' else 503
            value = dict(ok=False, failed=failed, bootstrap_phase=phase)
            return self.reply(code, json.dumps(value).encode() if self.path == '/health' else b'')

    def do_POST(self):
        if self.path != '/act':
            return self.reply(404, b'{}')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8 * 1024 * 1024:
                return self.reply(413, b'{"ok":false}')
            self.connection.settimeout(15)
            code, data = upstream('/act', self.rfile.read(size))
            return self.reply(code, data)
        except (OSError, ValueError):
            return self.reply(503, b'{"ok":false}')


def lifetime_bound():
    # Backend must ALSO install a detached guard that disables the endpoint
    # at the trial deadline. Process exit alone does not terminate GPU billing.
    time.sleep(int(os.environ.get('MAX_WORKER_LIFETIME_SECONDS', '3600')))
    if child is not None:
        child.terminate()
    os._exit(0)


if __name__ == '__main__':
    threading.Thread(target=lifetime_bound, daemon=True).start()
    threading.Thread(target=prepare, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '80'))), Handler).serve_forever()
