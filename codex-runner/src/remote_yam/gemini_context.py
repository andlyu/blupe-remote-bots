"""Sparse complete-call model input; the full run transcript is never trimmed.

Recompute from full history every request: an omitted age-four exchange must
reenter at age five. Native thoughts/calls/results are kept byte-for-byte as
JSON values, in chronological order. See docs/refs/gemini-argon/INDEX.md.
"""
import json

INPUT_TOKEN_BUDGET = 65536
RETAINED_CALL_AGES = (1, 2, 3, 5, 7, 10)
MAX_WIRE_BYTES = 8 * 1024 * 1024


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def estimated_tokens(wire):
    """Conservative sizing, NOT Google's tokenizer or billed token count.

    Charge one token per UTF-8 JSON byte, plus the documented 1,120 tokens for
    each explicitly high-resolution Gemini 4 image and 1,024 framing tokens.
    countTokens accepts Contents, not opaque Interactions steps; do not convert
    signed reasoning to a different API merely to obtain a token count.
    """
    images = 0
    def strip(value):
        nonlocal images
        if isinstance(value, dict):
            if value.get('type') == 'image':
                images += 1
                return {k: v for k, v in value.items() if k != 'data'}
            return {k: strip(v) for k, v in value.items()}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    compact = strip(wire)
    return len(encoded(compact)) + images * 1120 + 1024


def observation(item):
    return item.get('role') == 'user' and isinstance(item.get('content'), list)


def resolved(history):
    pending = set()
    for item in history:
        if item.get('type') == 'function_call':
            identity = item['call_id']
            if identity in pending:
                return False
            pending.add(identity)
        elif item.get('type') == 'function_call_output':
            if item['call_id'] not in pending:
                return False
            pending.remove(item['call_id'])
    return not pending


def select_history(history):
    starts = [i for i, item in enumerate(history) if observation(item)]
    completed, keep = [], set(range(starts[0] if starts else len(history)))
    for start, end in zip(starts, starts[1:] + [len(history)]):
        block = history[start:end]
        if not resolved(block):
            raise RuntimeError('Gemini cannot infer with an unresolved tool exchange')
        if any('_gemini_step' in item for item in block):
            completed.append((start, end))
        else:
            # The new observation and any newly included owner corrections.
            keep.update(range(start, end))
    numbers = []
    for number, (start, end) in enumerate(completed, 1):
        if len(completed) - number + 1 in RETAINED_CALL_AGES:
            keep.update(range(start, end))
            numbers.append(number)
    for index, item in enumerate(history):
        content = item.get('content')
        if item.get('role') == 'system' or (item.get('role') == 'user'
                and isinstance(content, str)
                and content.startswith(('Goal: ', 'Run-owner steering update #'))):
            # Owner messages have their own bounded inbox. Keep all corrections
            # verbatim, even when the associated model call is omitted.
            keep.add(index)
    return [item for i, item in enumerate(history) if i in keep], numbers


class GeminiContext:
    def __init__(self):
        self.selected_calls = []
        self.last_estimate = 0

    def prepare(self, payload, convert, *, pending=False):
        if pending:
            raise RuntimeError('Gemini cannot infer while motion is pending')
        selected, numbers = select_history(payload['input'])
        wire = convert({**payload, 'input': selected})
        estimate = estimated_tokens(wire)
        if estimate > INPUT_TOKEN_BUDGET or len(encoded(wire)) > MAX_WIRE_BYTES:
            # Preserve the exact user-selected pattern; never silently remove
            # another exchange, truncate native state, or replace it by a summary.
            raise RuntimeError('Gemini sparse history exceeds the context budget; no model call sent')
        self.selected_calls, self.last_estimate = numbers, estimate
        return wire
