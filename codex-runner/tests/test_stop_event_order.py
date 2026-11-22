"""A queued event already in transit cannot reactivate an acknowledged Stop."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest

from remote_yam.controller import RunnerController
from remote_yam.providers import ScriptedAdapter
from remote_yam.session import MockSessionAPI


class StopEventOrderTests(unittest.TestCase):
    def test_eight_late_active_events_do_not_reactivate_a_stopped_session(self):
        api = MockSessionAPI(auto_activate=False)
        controller = RunnerController(api)
        state = controller.join(ScriptedAdapter([]), 'Fixture task')
        sid = state['session_id']
        released = threading.Event()
        events = [('snapshot', {'status':'queued'}), ('snapshot', {'status':'running'}),
                  ('queue_update', {'position':1}), ('lifecycle', {'state':'preparing'})] * 2
        def receive(item):
            if not released.wait(3):
                raise RuntimeError('Fixture did not release delayed event')
            kind, payload = item
            controller._handle_event(dict(schema_version=1, session_id=sid, type=kind, payload=payload))
        with ThreadPoolExecutor(max_workers=8) as pool:
            pending = [pool.submit(receive, item) for item in events]
            try:
                self.assertEqual(controller.stop()['status'], 'stopped')
            finally:
                released.set()
            for future in pending:
                future.result()
        self.assertEqual(controller.status()['status'], 'stopped')
        self.assertFalse(api.action_log)
        # The stop latch belongs to the old session, not the next accepted run.
        self.assertEqual(controller.join(ScriptedAdapter([]), 'Next fixture task')['status'], 'queued')
        controller.stop()

    def test_late_terminal_receipts_still_retain_the_exact_episode(self):
        api = MockSessionAPI(auto_activate=False)
        controller = RunnerController(api)
        state = controller.join(ScriptedAdapter([]), 'Fixture task')
        controller.stop()
        controller._handle_event(dict(schema_version=1, session_id=state['session_id'],
            type='snapshot', payload=dict(status='stopped', episode_id='ep_fixture')))
        self.assertEqual(controller.status()['episode_id'], 'ep_fixture')
        self.assertEqual(controller.status()['status'], 'stopped')
