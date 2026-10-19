"""Small local timing receipts; callers provide only non-secret stage labels."""
from contextlib import contextmanager
import time


@contextmanager
def timed_span(spans, stage, **fields):
    started_at, started = time.time(), time.perf_counter()
    status = 'ok'
    try:
        yield
    except BaseException:
        status = 'error'
        raise
    finally:
        spans.append(dict(stage=stage, started_at=started_at,
                          duration_s=time.perf_counter()-started, status=status, **fields))


@contextmanager
def journal_span(sink, stage, **fields):
    """Emit local stage boundaries; a diagnostic sink cannot interrupt control."""
    started_at, started = time.time(), time.perf_counter()
    def emit(state, **extra):
        if callable(sink):
            try:
                sink('policy_timing', 'Policy stage: '+stage,
                     stage=stage, state=state, started_at=started_at, **fields, **extra)
            except Exception:
                pass
    emit('started')
    state = 'completed'
    try:
        yield
    except BaseException:
        state = 'error'
        raise
    finally:
        emit(state, duration_s=time.perf_counter()-started)
