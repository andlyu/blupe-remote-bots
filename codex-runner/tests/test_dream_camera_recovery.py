"""Exercise real camera HTTP retry exhaustion through Dream's input collector."""
import io
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image
import pytest

from remote_yam.cameras import CameraFrameSource
from test_dream_policy import adapter, observation


@pytest.fixture
def relay():
    image = io.BytesIO()
    Image.new('RGB', (32, 24), 'red').save(image, format='JPEG')
    class Handler(BaseHTTPRequestHandler):
        failures = 2
        status = 503
        right_requests = 0
        def do_GET(self):
            if self.path == '/right':
                type(self).right_requests += 1
                if self.right_requests <= self.failures:
                    self.send_error(self.status, 'private camera payload')
                    return
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(image.getvalue())))
            self.end_headers()
            self.wfile.write(image.getvalue())
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def provider_for_relay(tmp_path, relay):
    origin, handler = relay
    provider = adapter(tmp_path)
    provider.camera_source = CameraFrameSource(origin, max_attempts=2)
    provider.observation_source = lambda: dict(observation(), images={
        side: {'url': origin + '/' + side} for side in ('left', 'top', 'right')})
    return provider, handler


def test_transient_camera_exhaustion_pauses_and_uses_fresh_inputs(tmp_path, relay):
    provider, handler = provider_for_relay(tmp_path, relay)
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append((kind, details))
    try:
        points = provider.build_trajectory('move', observation(), 0)
        assert points and handler.right_requests >= 3
        assert any(kind == 'observation_retry' for kind, _ in events)
        # The model request can start only after a completely fresh capture.
        assert provider._failure is None
        requests = [payload for command, payload in provider._worker.calls if command == 'predict']
        assert len(requests) == 1
        assert all(tick['observed_at'] > 0 for tick in requests[0]['ticks'])
        assert 'private camera payload' not in str(events)
    finally:
        provider.close_transport()


def test_persistent_camera_exhaustion_is_bounded_and_never_predicts(tmp_path, relay, monkeypatch):
    monkeypatch.setattr('remote_yam.dream_policy.OBSERVATION_RECOVERY_S', .25)
    provider, handler = provider_for_relay(tmp_path, relay)
    handler.failures = 100
    provider.camera_source.max_attempts = 1
    events = []
    provider.interaction_sink = lambda kind, message, **details: events.append((kind, details))
    began = time.monotonic()
    try:
        with pytest.raises(RuntimeError, match='camera.*recovery timed out'):
            provider.build_trajectory('move', observation(), 0)
        assert time.monotonic() - began < 2
        assert not any(command == 'predict' for command, _ in provider._worker.calls)
        failure = next(details for kind, details in events if kind == 'observation_failure')
        assert failure['field'] == 'camera_right' and failure['http_status'] == 503
        assert not provider._history
    finally:
        provider.close_transport()


def test_camera_permission_denial_still_fails_immediately(tmp_path, relay):
    provider, handler = provider_for_relay(tmp_path, relay)
    handler.failures, handler.status = 100, 403
    try:
        with pytest.raises(RuntimeError, match='camera.*HTTP 403'):
            provider.build_trajectory('move', observation(), 0)
        assert handler.right_requests == 1
        assert not any(command == 'predict' for command, _ in provider._worker.calls)
    finally:
        provider.close_transport()


def test_terminal_input_diagnostic_is_retained_before_consumer_raises(tmp_path):
    provider = adapter(tmp_path)
    provider.observation_source = lambda: dict(observation(), left_gripper='invalid')
    reporting, release, finished = threading.Event(), threading.Event(), threading.Event()
    errors = []
    def sink(kind, message, **details):
        if kind == 'observation_failure':
            reporting.set()
            assert release.wait(2)
    provider.interaction_sink = sink
    def build():
        try:
            provider.build_trajectory('move', observation(), 0)
        except RuntimeError as error:
            errors.append(str(error))
        finally:
            finished.set()
    thread = threading.Thread(target=build)
    try:
        thread.start()
        assert reporting.wait(1)
        assert not finished.wait(.1)
        release.set()
        assert finished.wait(1) and errors
        assert 'left_gripper' in errors[0]
    finally:
        release.set()
        provider.close_transport()
        thread.join(2)
