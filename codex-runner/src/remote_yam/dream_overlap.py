"""Time-indexed Dream plans; inference never owns the motor dispatch clock."""
from copy import deepcopy
import math
import threading
import time


class PlanRejected(RuntimeError):
    """Existing native limits held the plan; ask for fresh measured input."""


class ChunkBuffer:
    def __init__(self, *, cadence_hz=10.):
        self.cadence_hz = cadence_hz
        self.lock = threading.Lock()
        self.plan = None
        self.sequence = -1
        self.expired = 0
        self.replacements = 0
        self.generation = 0

    def invalidate(self):
        with self.lock:
            self.plan = None
            self.generation += 1

    def replace(self, points, origin, sequence, now, generation=None):
        if (not points or not math.isfinite(origin) or origin > now
                or type(sequence) is not int):
            raise ValueError('Invalid timed Dream chunk')
        with self.lock:
            if generation is not None and generation != self.generation:
                return False
            if sequence <= self.sequence:
                return False
            self.sequence = sequence
            if now - origin >= len(points) / self.cadence_hz:
                self.expired += 1
                return False
            self.plan = (origin, deepcopy(points))
            self.replacements += 1
            return True

    def target(self, now):
        with self.lock:
            if self.plan is None:
                return None
            origin, points = self.plan
            index = math.floor((now - origin) * self.cadence_hz + 1e-8)
            if not 0 <= index < len(points):
                return None
            return deepcopy(points[index])


class OverlapLoop:
    """One prediction in flight, at most one new request per second.

    A slow request delays the next request, never accumulates a request queue.
    Plans are indexed from their observation, not from their arrival. Exhausted
    plans retain the last command until a fresh plan or the existing Stop path.
    """
    def __init__(self, *, predict, play, cancelled, budget, period=1.,
                 clock=time.monotonic, wait=None, on_prediction=None):
        self.predict, self.play = predict, play
        self.cancelled, self.budget = cancelled, budget
        self.period, self.clock = period, clock
        self.stop = threading.Event()
        self.wait = wait or self.stop.wait
        self.on_prediction = on_prediction or (lambda **kw: None)
        self.buffer = ChunkBuffer()
        self.failure = None
        self.predictions = self.waypoints = self.underflow_ticks = 0
        self.rejected_plans = 0
        self.latencies = []
        self.prediction_times = []
        self.dispatch_times = []
        self.thread = None

    def stopped(self):
        return self.stop.is_set() or self.cancelled()

    def _predict(self):
        sequence = 0
        try:
            while not self.stopped():
                started = self.clock()
                self.prediction_times.append(started)
                self.prediction_times[:] = self.prediction_times[-100:]
                generation = self.buffer.generation
                try:
                    points, origin = self.predict()
                except PlanRejected:
                    points, origin = [], started
                    self.rejected_plans += 1
                if self.stopped():
                    return
                finished = self.clock()
                installed = bool(points) and self.buffer.replace(points, origin, sequence, finished, generation)
                self.predictions += 1
                self.latencies.append(finished - started)
                self.latencies[:] = self.latencies[-100:]
                self.on_prediction(installed=installed, latency_s=finished-started,
                                   predictions=self.predictions)
                sequence += 1
                self.wait(max(0., started + self.period - self.clock()))
        except Exception as error:
            self.failure = error
            self.stop.set()

    def run(self):
        if self.budget <= 0 or self.stopped():
            return
        self.thread = threading.Thread(target=self._predict, daemon=True,
                                       name='dream-overlap-predict')
        self.thread.start()
        last = None
        try:
            while not self.stopped() and self.waypoints < self.budget:
                target = self.buffer.target(self.clock())
                if target is None:
                    if last is None:
                        self.wait(.01)
                        continue
                    self.underflow_ticks += 1
                    target = last
                if self.stopped():
                    break
                # play owns normal native cadence/validation, not this thread.
                try:
                    self.play(target)
                except PlanRejected:
                    # Native dispatch retained its last safe command. Clear the
                    # old plan and any inference started before that hold.
                    self.buffer.invalidate()
                    self.rejected_plans += 1
                    last = None
                    self.wait(.01)
                    continue
                self.dispatch_times.append(self.clock())
                self.dispatch_times[:] = self.dispatch_times[-100:]
                self.waypoints += 1
                last = target
            if self.failure is not None:
                raise self.failure
        finally:
            self.stop.set()

    def status(self):
        def rate(stamps):
            span = stamps[-1]-stamps[0] if len(stamps) > 1 else 0.
            return (len(stamps)-1)/span if span > 0 else None
        return dict(replan_hz=1/self.period, predictions=self.predictions,
                    waypoints=self.waypoints, underflow_ticks=self.underflow_ticks,
                    expired_chunks=self.buffer.expired,
                    rejected_plans=self.rejected_plans,
                    chunk_replacements=self.buffer.replacements,
                    achieved_prediction_hz=rate(self.prediction_times),
                    achieved_control_hz=rate(self.dispatch_times),
                    prediction_s=self.latencies[-1] if self.latencies else None)
