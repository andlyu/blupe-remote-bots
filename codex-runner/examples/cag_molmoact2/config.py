"""Build private provider payloads. No API calls or credential access.

Provider schemas are vendored in docs/refs/runpod. The backend owns resource
creation, names, deadlines and cleanup; generated endpoints start disabled.
"""
import base64
import json
from pathlib import Path
import zlib

HERE = Path(__file__).resolve().parent
IMAGE = 'pytorch/pytorch@sha256:cf5aa3f7045a68c10d80f546746591c5ccae6a33729e5e32625ff76bd2c036fe'
# Existing verified model/runtime volume is supplied explicitly at deployment.


def encoded_command(names, main):
    bundle = {name: ((HERE.parents[1] / 'src/remote_yam/molmoact_protocol.py') if name == 'protocol.py' else HERE / name).read_text() for name in names}
    encoded = base64.b64encode(zlib.compress(json.dumps(bundle).encode())).decode()
    source = (HERE / main).read_text()
    program = base64.b64encode(zlib.compress(source.encode())).decode()
    loader = ('import pathlib,json,base64,zlib; p=pathlib.Path("/tmp/molmoact2-app");'
              'p.mkdir(exist_ok=True);'
              f'(p/"bundle.json").write_bytes(zlib.decompress(base64.b64decode({encoded!r})));'
              f'exec(compile(zlib.decompress(base64.b64decode({program!r})),{main!r},"exec"),{{"__name__":"__main__"}})')
    compile(loader, '<private-container-command>', 'exec')
    return [loader]


def gpu_config(volume_id, name='molmoact2-yam1', data_center='US-CA-2'):
    return dict(name=name, type='LOAD_BALANCER', image=IMAGE,
                entrypoint=['python', '-u', '-c'],
                cmd=encoded_command(('worker.py', 'protocol.py', 'guidance.py', 'requirements.txt'), 'bootstrap.py'),
                disk=40, ports=[],
                env={'PORT': '80', 'PORT_HEALTH': '80', 'HEALTH_CHECK_PATH': '/ping',
                     'PYTHONUNBUFFERED': '1', 'HF_HOME': '/runpod-volume/molmoact2-hf-cache',
                     'HF_HUB_DISABLE_PROGRESS_BARS': '1', 'TOKENIZERS_PARALLELISM': 'false',
                     'OMP_NUM_THREADS': '8', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
                     'MAX_WORKER_LIFETIME_SECONDS': '3600'},
                gpu={'pools': ['ADA_24'], 'count': 1, 'minCudaVersion': '12.9'},
                workers={'min': 0, 'max': 0, 'idleTimeout': 300},
                scaling={'type': 'REQUEST_COUNT', 'requestCount': 1},
                networkVolumes=[volume_id], dataCenterIds=[data_center],
                timeout=300000, flashboot='FLASHBOOT')
