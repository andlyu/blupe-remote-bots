"""Bounded run-owner messages, consumed only by the policy's inference thread."""
import re
import threading
import time


STEERING_INSTRUCTIONS = (
    '\n\nThe run owner may send steering updates as additional user turns. '
    'Use them to revise your next decision in the existing task and observation context. '
    'Newer updates supersede conflicting earlier task instructions, including the original goal. '
    'A relative correction requests a change once, not repetition on every turn. '
    'Steering does not change tool contracts, safety limits, or the requirement to verify '
    'motion using measured feedback. Never claim an update was executed until feedback confirms it.'
)


class SteeringError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class SteeringInbox:
    def __init__(self, emit):
        self._lock = threading.RLock()
        self._messages = []
        self._emit = emit
        self._last_submitted = None
        self._instructions_included = False

    def submit(self, text, request_id):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise SteeringError(400, 'Enter a steering message of 1–2,000 characters')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', request_id):
            raise SteeringError(400, 'A valid steering request ID is required')
        text = text.strip()
        with self._lock:
            for row in self._messages:
                if row['request_id'] == request_id:
                    if row['text'] != text:
                        raise SteeringError(409, 'This steering request ID was already used')
                    return dict(row)
            if (len(self._messages) >= 32 or
                    sum(len(row['text']) for row in self._messages) + len(text) > 16000):
                raise SteeringError(429, 'This run reached its steering message limit')
            if sum(row['state'] == 'queued' for row in self._messages) >= 8:
                raise SteeringError(429, 'Wait for the model to read the queued steering messages')
            now = time.monotonic()
            if self._last_submitted is not None and now - self._last_submitted < 1:
                raise SteeringError(429, 'Wait a moment before sending another steering message')
            row = dict(id=len(self._messages) + 1, request_id=request_id, text=text,
                       state='queued', submitted_at=time.time(), included_at=None)
            self._messages.append(row)
            self._last_submitted = now
            self._emit('steering_queued', text, steering_id=row['id'])
            return dict(row)

    def pending(self):
        with self._lock:
            return any(row['state'] == 'queued' for row in self._messages)

    def include_prompt(self, original_goal):
        """Consume queued corrections into a policy's single language input."""
        with self._lock:
            queued = [row for row in self._messages if row['state'] == 'queued']
            if not queued:
                return None
            prompt = (original_goal + '\n\nRun-owner guidance (newer updates take precedence '
                      'over conflicting earlier instructions):\n' + '\n'.join(
                          f"{row['id']}. {row['text']}" for row in self._messages
                          if row['state'] in {'queued', 'included'}))
            for row in queued:
                row.update(state='included', included_at=time.time())
                self._emit('steering_included', 'Steering included in model context',
                           steering_id=row['id'])
            return prompt

    def include(self, history):
        """Append user turns without mutating history from the HTTP thread."""
        with self._lock:
            for row in self._messages:
                if row['state'] != 'queued':
                    continue
                if not self._instructions_included:
                    history.append({'role': 'system', 'content': STEERING_INSTRUCTIONS.strip()})
                    self._instructions_included = True
                history.append({'role': 'user', 'content':
                    f"Run-owner steering update #{row['id']}:\n{row['text']}"})
                row.update(state='included', included_at=time.time())
                self._emit('steering_included', 'Steering included in model context',
                           steering_id=row['id'])

    def snapshot(self, *, active=True):
        with self._lock:
            return [dict(row, state='not_delivered' if not active and row['state'] == 'queued'
                         else row['state']) for row in self._messages]

    def acknowledge(self, request_ids):
        """Remote coding workers acknowledge delivery in an observation."""
        with self._lock:
            for row in self._messages:
                if row['state'] == 'queued' and row['request_id'] in request_ids:
                    row.update(state='included', included_at=time.time())
                    self._emit('steering_included', 'Correction delivered in the agent observation', steering_id=row['id'])
