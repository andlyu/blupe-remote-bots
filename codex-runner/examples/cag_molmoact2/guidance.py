"""Paper-derived experimental port; never presented as official CAG code.

v1: per action-expert layer/flow step, average current unmodified cross-attention
probabilities over heads and action queries; select ceil(25% of task tokens).
Scale only selected normalized projected K and V by (1 + alpha). No mutation
of cached context, image tokens, discrete state, or the VLM vision branch.
"""
from contextlib import contextmanager
import math
from pathlib import Path
import torch

VARIANT = 'cag-inspired-molmoact2-v1'
SPEC = dict(status='paper-derived experimental port; not an exact CAG reproduction',
    gate='top ceil(0.25 * task_token_count), stable token-order ties',
    score='mean over heads and action queries of unmodified QK softmax over all valid keys',
    layers='all 36 action-expert cross-attention layers', refresh='each layer at each flow step',
    scale='selected task-text projected normalized K and V multiplied by 1 + alpha',
    alpha_range=[0.0, 0.30], cuda_graph=False)


def options(payload):
    mode = payload.get('mode', 'baseline')
    strength = payload.get('guidance_strength', 0.15 if mode == 'guided' else 0.0)
    seed = payload.get('seed', 0)
    if mode not in ('baseline', 'guided'):
        raise ValueError('Choose baseline or guided')
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= .30:
        raise ValueError('Guidance strength must be between 0 and 0.30')
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise ValueError('Seed must be an integer in [0, 2**31)')
    return mode, float(strength) if mode == 'guided' else 0.0, seed


def task_indices(text, task, encoded, input_ids):
    """Map offset-labelled lexical task tokens into expanded multimodal IDs.

    Fail closed if the exact token subsequence is missing/ambiguous. Offsets are
    measured before image expansion; subsequence matching locates the unchanged
    task in the actual processor output, never guesses image-token lengths.
    """
    marker = 'The task is to '
    begin = text.index(marker) + len(marker)
    end = begin + len(task)
    if not task or text[begin:end] != task or text[end:end+15] != '. The setup is ':
        raise ValueError('Unexpected pinned task prompt format')
    positions = [i for i, (a, b) in enumerate(encoded.offsets) if a < end and b > begin]
    if not positions:
        raise ValueError('No eligible task tokens')
    ids = encoded.ids[positions[0]:positions[-1]+1]
    matches = [i for i in range(len(input_ids)-len(ids)+1) if input_ids[i:i+len(ids)] == ids]
    if len(matches) != 1:
        raise ValueError('Ambiguous task token mapping')
    return list(range(matches[0], matches[0]+len(ids)))


class ProcessorProxy:
    def __init__(self, processor, guidance, task):
        self.processor, self.guidance, self.task = processor, guidance, task

    def __getattr__(self, name):
        return getattr(self.processor, name)

    def __call__(self, *args, **kwargs):
        result = self.processor(*args, **kwargs)
        if (self.guidance.active and self.guidance.active['mode'] == 'guided'
                and self.guidance.active['strength'] != 0):
            from tokenizers import Tokenizer
            if self.guidance.tokenizer is None:
                self.guidance.tokenizer = Tokenizer.from_file('/runpod-volume/molmoact2-yam/tokenizer.json')
            text = kwargs['text']
            encoded = self.guidance.tokenizer.encode(text, add_special_tokens=False)
            indices = task_indices(text, self.task, encoded, result['input_ids'][0].tolist())
            self.guidance.active['indices'] = indices
            self.guidance.active['context_length'] = result['input_ids'].shape[-1]
        return result


class Guidance:
    # Policy's lock encloses every complete request. Hooks are instance-local;
    # finally clears all request state, including after processor/model errors.
    def __init__(self, model):
        self.model, self.active, self.tokenizer = model, None, None
        self.last_receipt = {}
        self.installed = False

    def install(self):
        if self.installed:
            raise RuntimeError('Hooks already installed')
        blocks = self.model.model.action_expert.blocks
        if len(blocks) != 36:
            raise RuntimeError('Pinned 36-layer action expert required')
        for layer, block in enumerate(blocks):
            original = block.cross_attn._attention
            def attention(q, k, v, *, attn_mask=None, original=original, layer=layer):
                run = self.active
                if run is None or run['mode'] == 'baseline' or run['strength'] == 0:
                    return original(q, k, v, attn_mask=attn_mask)
                if k.shape[0] != 1 or k.shape[1] != run.get('context_length') or not run.get('indices'):
                    raise ValueError('Task mask does not match projected context')
                idx = torch.tensor(run['indices'], device=k.device, dtype=torch.long)
                logits = torch.matmul(q.transpose(1, 2).float(), k.transpose(1, 2).float().transpose(-1, -2)) / math.sqrt(q.shape[-1])
                if attn_mask is not None:
                    if attn_mask.dtype == torch.bool:
                        logits = logits.masked_fill(~attn_mask, float('-inf'))
                    else:
                        logits = logits + attn_mask.float()
                scores = logits.softmax(-1).mean(dim=(0, 1, 2)).index_select(0, idx)
                chosen = idx[torch.argsort(scores, descending=True, stable=True)[:max(1, math.ceil(len(idx)*.25))]]
                scale = torch.ones(k.shape[1], device=k.device, dtype=k.dtype)
                scale[chosen] = 1 + run['strength']
                scaled_k, scaled_v = k * scale[None, :, None, None], v * scale[None, :, None, None]
                # Actual GPU evidence on first call; all subsequent calls use
                # this same out-of-place operation. Includes image/state keys.
                if run['calls'] == 0:
                    other = torch.ones(k.shape[1], device=k.device, dtype=torch.bool)
                    other[idx] = False
                    run['non_goal_kv_unchanged'] = bool(torch.equal(k[:, other], scaled_k[:, other]) and torch.equal(v[:, other], scaled_v[:, other]))
                    if not run['non_goal_kv_unchanged']:
                        raise RuntimeError('Non-task context changed')
                delta = (scaled_k[:, chosen].float()-k[:, chosen].float()).abs().sum() + (scaled_v[:, chosen].float()-v[:, chosen].float()).abs().sum()
                run['delta'] = delta if run['delta'] is None else run['delta'] + delta
                run['calls'] += 1
                run['scaled_text_tokens'] += len(chosen)
                run['layers'].add(layer)
                return original(q, scaled_k, scaled_v, attn_mask=attn_mask)
            block.cross_attn._attention = attention
        self.installed = True

    @contextmanager
    def request(self, mode, strength):
        if self.active is not None:
            raise RuntimeError('Concurrent guidance state')
        run = dict(mode=mode, strength=strength, calls=0, scaled_text_tokens=0,
                   layers=set(), delta=None, non_goal_kv_unchanged=True)
        self.active = run
        try:
            yield
        finally:
            self.last_receipt = dict(variant=VARIANT, mode=mode, effective_strength=strength,
                calls=run['calls'], eligible_task_tokens=len(run.get('indices', [])),
                scaled_text_tokens=run['scaled_text_tokens'], layers=sorted(run['layers']),
                kv_delta_l1=0.0 if run['delta'] is None else float(run['delta'].item()),
                non_goal_kv_unchanged=run['non_goal_kv_unchanged'])
            self.active = None
