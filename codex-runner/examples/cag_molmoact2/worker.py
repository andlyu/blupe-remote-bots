"""GPU-only MolmoAct2 inference, loopback HTTP, and no robot IO.

Loading/prediction follow the pinned checkpoint README and the canonical
examples/yam/host_server_yam.py@66b87e64efd99dfd103241418113955cf64dfa9c.
Unlike that reference, a failed real CUDA warmup never advertises readiness.
"""
import io
import hashlib
import sys
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image
import torch
from transformers import AutoModelForImageTextToText, AutoProcessor

from guidance import Guidance, ProcessorProxy, options, VARIANT, SPEC

from protocol import (ACTION_DIM, CAMERAS, MAX_BODY, NORM_TAG, NUM_ACTIONS,
                      identity, validate_actions, validate_payload)

ROOT = Path('/runpod-volume/molmoact2-yam')
Image.MAX_IMAGE_PIXELS = 16_000_000


class Policy:
    def __init__(self):
        self.ready = False
        self.failed = False
        self.lock = threading.Lock()
        started = time.monotonic()
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA is required; CPU execution is forbidden')
        self.device = torch.device('cuda:0')
        torch.cuda.set_device(self.device)
        torch.cuda.reset_peak_memory_stats(self.device)
        self.processor = AutoProcessor.from_pretrained(
            str(ROOT), trust_remote_code=True, local_files_only=True,
            extra_special_tokens={}, use_fast=False)
        self.model = AutoModelForImageTextToText.from_pretrained(
            str(ROOT), trust_remote_code=True, local_files_only=True,
            dtype=torch.bfloat16).to(self.device).eval().requires_grad_(False)
        if int(self.model.config.max_action_horizon) != NUM_ACTIONS:
            raise RuntimeError('Unexpected checkpoint action horizon')

        # The canonical server casts floating processor tensors as well as
        # moving them. Keep the pinned source itself pristine.
        def move_and_cast(inputs, device):
            result = {}
            for key, value in inputs.items():
                if torch.is_tensor(value):
                    value = value.to(device)
                    if value.is_floating_point():
                        value = value.to(torch.bfloat16)
                result[key] = value
            return result

        self.model._move_inputs_to_device = move_and_cast
        # Use the checkpoint's real documented sample rather than guessing
        # camera dimensions or treating zero-state synthetic outputs as safe.
        state = [-0.06656748056411743, 0.014686808921396732, 0.016594186425209045,
                 -0.08602273464202881, -0.014686808921396732, 0.13904783129692078,
                 0.9922363758087158, 0.19512474536895752, 0.010872052982449532,
                 0.010872052982449532, -0.06771191209554672, -0.07305257022380829,
                 -0.08945601433515549, 0.9888537526130676]
        images = [Image.open(ROOT / f'assets/sample_{name}_rgb.png').convert('RGB') for name in CAMERAS]
        task = 'Place cups and plate in dishwasher rack, dispose of food waste, and organize remaining items.'
        self.guidance = Guidance(self.model)
        self.warmup_seconds = []
        # Compare a pristine, unpatched model first. Hooks are installed only
        # afterwards; seed, precision, steps and eager sampling stay identical.
        pristine, _, _ = self.predict(images, state, task)
        self.guidance.install()
        baseline, elapsed, _ = self.predict(images, state, task)
        zero, elapsed0, zero_meta = self.predict(images, state, task, 'guided', 0.0)
        guided, elapsed1, meta = self.predict(images, state, task, 'guided', 0.15)
        if pristine != baseline or pristine != zero:
            raise RuntimeError('Strength-zero parity with pristine baseline failed')
        if meta['calls'] != 360 or len(meta['layers']) != 36 or not meta['scaled_text_tokens'] or not meta['kv_delta_l1'] > 0:
            raise RuntimeError('Nonzero guidance failed to change text conditioning')
        self.verification = dict(pristine_baseline_equal=True, zero_strength_exact_equal=True,
            nonzero_text_kv_changed=True, non_goal_kv_unchanged=meta['non_goal_kv_unchanged'],
            action_max_abs_delta=max(abs(a-b) for x,y in zip(baseline,guided) for a,b in zip(x,y)),
            baseline_seconds=elapsed, zero_seconds=elapsed0, guided_seconds=elapsed1,
            guidance=meta, seed=0, sample='checkpoint documented dishwasher images/state')
        self.warmup_seconds = [elapsed, elapsed0, elapsed1]
        self.model_startup_seconds = time.monotonic() - started
        self.check_headroom()
        self.ready = True
        receipt = self.health()
        Path('/tmp/molmoact2-app/last-warmup.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(dict(event='real_cuda_warmup_complete', **receipt)), flush=True)

    def check_headroom(self):
        free, total = torch.cuda.mem_get_info(self.device)
        if free < max(total * 0.20, 4 * 1024 ** 3):
            raise RuntimeError('Insufficient GPU headroom after real inference')

    def predict(self, images, state, instruction, mode="baseline", strength=0.0, seed=0):
        if not torch.cuda.is_available() or next(self.model.parameters()).device != self.device:
            raise RuntimeError('CUDA model placement was lost')
        started = time.monotonic()
        with self.lock:
            with self.guidance.request(mode, strength), torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
                output = self.model.predict_action(
                    processor=ProcessorProxy(self.processor, self.guidance,
                        sys.modules[type(self.model).__module__]._normalize_question_text(instruction)), images=images,
                    task=instruction, state=np.asarray(state, dtype=np.float32),
                    norm_tag=NORM_TAG, inference_action_mode='continuous',
                    enable_depth_reasoning=False, num_steps=10,
                    normalize_language=True, enable_cuda_graph=False,
                    generator=torch.Generator(device=self.device).manual_seed(seed))
                torch.cuda.synchronize(self.device)
                actions = output.actions.detach().to(device='cpu', dtype=torch.float32).numpy()
            if actions.shape == (1, NUM_ACTIONS, ACTION_DIM):
                actions = actions[0]
            if actions.shape != (NUM_ACTIONS, ACTION_DIM) or not np.isfinite(actions).all():
                raise RuntimeError('Unexpected/non-finite model action chunk')
            # No endpoint clamp or unit reinterpretation: reject the entire chunk
            # if its raw robot-scale grippers violate the YAM1 contract.
            values = validate_actions(actions.tolist())
            self.check_headroom()
            return values, time.monotonic() - started, self.guidance.last_receipt

    def health(self):
        free, total = torch.cuda.mem_get_info(self.device)
        return dict(identity(), ok=self.ready and not self.failed,
                    failed=self.failed, cuda_available=torch.cuda.is_available(),
                    device=str(self.device), gpu=torch.cuda.get_device_name(self.device),
                    dtype='bfloat16', enable_cuda_graph=False, variant=VARIANT, intervention=SPEC,
                    verification=getattr(self, 'verification', None),
                    model_startup_seconds=getattr(self, 'model_startup_seconds', None),
                    warmup_seconds=getattr(self, 'warmup_seconds', []),
                    peak_allocated_gb=torch.cuda.max_memory_allocated(self.device) / 1e9,
                    peak_reserved_gb=torch.cuda.max_memory_reserved(self.device) / 1e9,
                    free_vram_gb=free / 1e9, total_vram_gb=total / 1e9)

    def act(self, payload):
        instruction, state, encoded = validate_payload(payload)
        mode, strength, seed = options(payload)
        images = []
        for data in encoded:
            with Image.open(io.BytesIO(data)) as source:
                if source.format != 'JPEG' or source.width > 4096 or source.height > 4096:
                    raise ValueError('Expected JPEGs no larger than 4096 pixels per side')
                images.append(source.convert('RGB'))
        if not self.ready or self.failed:
            raise RuntimeError('Model is not ready')
        try:
            actions, elapsed, experiment = self.predict(images, state, instruction, mode, strength, seed)
        except ValueError:
            # A rejected scene/chunk does not invalidate an otherwise healthy
            # immutable CUDA model. Return no actions and retain readiness.
            raise
        except Exception:
            self.failed = True
            raise
        return dict(identity(), ok=True, device=str(self.device),
                    cuda_available=True, actions=actions, inference_seconds=elapsed,
                    experiment=dict(experiment, seed=seed, num_steps=10, dtype='bfloat16',
                        enable_cuda_graph=False, revision=identity()['revision'],
                        image_sha256=[hashlib.sha256(data).hexdigest() for data in encoded],
                        state_sha256=hashlib.sha256(json.dumps(state).encode()).hexdigest(),
                        instruction_sha256=hashlib.sha256(instruction.encode()).hexdigest()))


def handler_for(policy):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, code, value):
            data = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path != '/health':
                return self.reply(404, {'ok': False})
            self.reply(200 if policy.ready and not policy.failed else 503, policy.health())

        def do_POST(self):
            if self.path != '/act':
                return self.reply(404, {'ok': False})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY:
                    raise ValueError('Invalid request size')
                self.connection.settimeout(15)
                payload = json.loads(self.rfile.read(size))
                self.reply(200, policy.act(payload))
            except (ValueError, KeyError):
                self.reply(422, dict(identity(), ok=False, error='invalid_input_or_actions'))
            except Exception as exc:
                print(json.dumps(dict(event='inference_failed', error=type(exc).__name__)), flush=True)
                self.reply(503, dict(identity(), ok=False, error='inference_failed'))
    return Handler


if __name__ == '__main__':
    policy = Policy()
    ThreadingHTTPServer(('127.0.0.1', 8202), handler_for(policy)).serve_forever()
