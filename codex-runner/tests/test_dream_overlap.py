import threading
import time

import pytest

from remote_yam.dream_overlap import ChunkBuffer, OverlapLoop


def rows(count=24):
    return [dict(row=i) for i in range(count)]


def test_late_chunk_uses_observation_clock_and_never_replays_elapsed_rows():
    buffer = ChunkBuffer()
    assert buffer.replace(rows(), 10., 0, 10.8)
    assert buffer.target(10.8) == {'row': 8}
    assert buffer.target(12.39) == {'row': 23}
    assert buffer.target(12.4) is None


def test_expired_or_out_of_order_reply_cannot_replace_a_valid_plan():
    buffer = ChunkBuffer()
    assert not buffer.replace(rows(), 0., 0, 2.4)
    assert buffer.expired == 1
    assert buffer.replace(rows(), 2., 2, 2.5)
    assert not buffer.replace([{'row': 999}], 2.5, 1, 2.5)
    assert buffer.target(2.5) == {'row': 5}


def test_input_and_output_are_isolated_from_plan_buffer():
    buffer = ChunkBuffer()
    points = rows()
    buffer.replace(points, 0., 0, 0.)
    points[0]['row'] = 999
    point = buffer.target(0.)
    point['row'] = 100
    assert buffer.target(0.) == {'row': 0}


@pytest.mark.parametrize('latency,expected', [(.2, [0., 1., 2.]), (1.4, [0., 1.4, 2.8])])
def test_pacer_never_overlaps_requests_or_queues_catchup_requests(latency, expected):
    now, starts = [0.], []
    loop = None
    def predict():
        starts.append(now[0])
        origin = now[0]
        now[0] += latency
        return rows(), origin
    def reported(**kw):
        if kw['predictions'] == 3:
            loop.stop.set()
    def wait(duration): now[0] += duration
    loop = OverlapLoop(predict=predict, play=lambda row: None, cancelled=lambda: False,
                       budget=100, clock=lambda: now[0], wait=wait, on_prediction=reported)
    loop._predict()
    assert starts == pytest.approx(expected)
    assert loop.predictions == 3


def test_motion_keeps_playing_while_next_prediction_is_blocked():
    blocked, release = threading.Event(), threading.Event()
    played = []
    calls = 0
    def predict():
        nonlocal calls
        calls += 1
        if calls == 2:
            blocked.set()
            assert release.wait(2)
        return rows(), time.monotonic()
    def play(row):
        played.append(row)
        time.sleep(.005)
    loop = OverlapLoop(predict=predict, play=play, cancelled=lambda: False,
                       budget=30, period=.01)
    thread = threading.Thread(target=loop.run)
    thread.start()
    assert blocked.wait(1)
    count = len(played)
    deadline = time.monotonic()+1
    while len(played) < count+4 and time.monotonic() < deadline:
        time.sleep(.005)
    assert len(played) >= count+4
    loop.stop.set()
    release.set()
    thread.join(1)
    loop.thread.join(1)
    assert not thread.is_alive() and not loop.thread.is_alive()


def test_cancel_discards_a_reply_that_arrives_after_stop():
    entered, release = threading.Event(), threading.Event()
    def predict():
        entered.set()
        release.wait(1)
        return rows(), time.monotonic()
    loop = OverlapLoop(predict=predict, play=lambda row: pytest.fail('No command after Stop'),
                       cancelled=lambda: False, budget=10)
    thread = threading.Thread(target=loop.run)
    thread.start()
    assert entered.wait(1)
    loop.stop.set()
    thread.join(1)
    release.set()
    loop.thread.join(1)
    assert loop.buffer.plan is None


def test_model_failure_is_propagated_without_motion():
    def predict(): raise ValueError('prediction failed')
    loop = OverlapLoop(predict=predict, play=lambda row: pytest.fail('No plan'),
                       cancelled=lambda: False, budget=10)
    with pytest.raises(ValueError, match='prediction failed'):
        loop.run()
