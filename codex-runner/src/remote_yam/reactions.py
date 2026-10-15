"""Bounded, in-memory reactions for one playground's visitor chat.

The runner's HTTP event loop owns this stream, just like its visitor sessions.
Reactions never enter the durable chat log or robot conversation.
"""
from collections import deque
import time


EMOJIS = frozenset(('🙂', '😂', '😠', '😢'))


class Reactions:
    lifetime = 5.0

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.cursor = 0
        self.events = deque(maxlen=128)

    def publish(self, emoji, visitor):
        self.cursor += 1
        self.events.append((self.clock(), dict(id=self.cursor, emoji=emoji, visitor=visitor)))
        return self.snapshot()[-1]

    def snapshot(self):
        now = self.clock()
        while self.events and now - self.events[0][0] >= self.lifetime:
            self.events.popleft()
        return [dict(event, remaining_ms=round((self.lifetime - (now - at)) * 1000))
                for at, event in self.events]
