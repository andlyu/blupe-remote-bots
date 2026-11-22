"""Server-owned sequential prompt batches through the normal admission path."""
import asyncio
from contextvars import ContextVar
import time

submission_batch = ContextVar('submission_batch', default=None)


def prompts_from(payload):
    prompts = payload.get('prompts')
    if not isinstance(prompts, list) or not 2 <= len(prompts) <= 10:
        raise ValueError('Queue between 2 and 10 prompts at a time')
    if any(not isinstance(p, str) or not 1 <= len(p.strip()) <= 4000 for p in prompts):
        raise ValueError('Each prompt must contain 1–4,000 characters')
    if sum(len(p) for p in prompts) > 16000:
        raise ValueError('Keep the batch within 16,000 characters')
    return [p.strip() for p in prompts]


class PromptBatch:
    def __init__(self, visitor, payload, prompts, submit, remember, *, poll_s=.2):
        self.visitor, self.submit, self.remember = visitor, submit, remember
        self.payload = {k: v for k, v in payload.items() if k != 'prompts'}
        self.jobs = [dict(prompt=p, status='pending') for p in prompts]
        self.index, self.phase, self.error = 0, 'starting', None
        self.cancelled, self.task, self.poll_s = False, None, poll_s

    @property
    def active(self):
        return self.phase in {'starting', 'running', 'stopping'}

    def snapshot(self):
        return dict(active=self.active, phase=self.phase, current=self.index + 1,
                    total=len(self.jobs), jobs=[dict(job) for job in self.jobs], error=self.error)

    def cancel(self):
        self.cancelled = True
        if self.active:
            self.phase = 'stopping'
        for job in self.jobs:
            if job['status'] == 'pending':
                job['status'] = 'cancelled'

    async def _launch(self):
        if self.cancelled or self.visitor.retired:
            return None
        job = self.jobs[self.index]
        # A fresh adapter/session and the exact same selected configuration for
        # every prompt. Admission, allowance, queue/lease and limits stay intact.
        token = submission_batch.set(self)
        try:
            result = await self.submit({**self.payload, 'prompt': job['prompt']})
        finally:
            submission_batch.reset(token)
        state = self.visitor.controller.status()
        job.update(status=state['status'], attempt_id=state.get('attempt_id'),
                   session_id=state.get('session_id'), episode_id=state.get('episode_id'))
        if self.cancelled or self.visitor.retired:
            await asyncio.to_thread(self.visitor.controller.stop, 'user_requested')
        return result

    async def start(self):
        try:
            result = await self._launch()
        except BaseException as exc:
            self.cancelled = True
            self.error = getattr(exc, 'message', 'The batch could not join the queue.')
            self.jobs[0]['status'] = 'rejected'
            self.submit = None
            self.phase = 'failed'
            self.payload.clear()
            raise
        self.phase = 'stopping' if self.cancelled else 'running'
        self.task = asyncio.create_task(self._advance())
        return {**(result or {}), 'prompt_batch': self.snapshot()}

    async def _advance(self):
        try:
            while True:
                self.visitor.touched = time.monotonic()
                state = self.visitor.controller.status()
                job = self.jobs[self.index]
                job.update(status=state['status'], session_id=state.get('session_id'),
                           episode_id=state.get('episode_id'))
                if self.visitor.controller.busy() or state['status'] in {'queued', 'preparing', 'running'}:
                    await asyncio.sleep(self.poll_s)
                    continue
                await asyncio.to_thread(self.remember, self.visitor)
                if self.cancelled or self.visitor.retired:
                    self.cancel()
                    self.phase = 'cancelled'
                    return
                if state.get('safety_error') or state['status'] in {'safety_aborted', 'disconnected'}:
                    self.error = 'Batch paused after a safety stop or lost connection. Review the run before submitting the remaining prompts.'
                    self.phase = 'failed'
                    return
                if self.index == len(self.jobs) - 1:
                    self.phase = 'complete'
                    return
                # Respect the existing five-second launch interval without
                # depending on a browser tab remaining open or polling status.
                delay = self.visitor.last_launch + 5 - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(min(delay, self.poll_s))
                    continue
                self.index += 1
                await self._launch()
                if self.cancelled:
                    self.phase = 'cancelled'
                    return
        except asyncio.CancelledError:
            self.cancel()
            self.phase = 'cancelled'
            raise
        except Exception as exc:
            self.jobs[self.index]['status'] = 'rejected'
            # RequestError messages are already safe for the owning browser.
            self.error = getattr(exc, 'message', 'The next prompt could not join the queue. Review it and submit again.')
            self.phase = 'failed'
        finally:
            self.payload.clear()  # Drop the captured provider key and contacts.
            self.submit = None
