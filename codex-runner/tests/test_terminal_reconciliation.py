import time
from unittest.mock import Mock
from remote_yam.controller import RunnerController
from remote_yam.providers import ScriptedAdapter
from remote_yam.session import MockSessionAPI


def running():
    api=MockSessionAPI(auto_activate=False)
    controller=RunnerController(api)
    controller.join(ScriptedAdapter([]),'Test recorded session',run_duration_s=60)
    controller._status='running'
    controller._run_started_at=time.time()-61
    api.stop_session=Mock(wraps=api.stop_session)
    return controller,api


def test_missing_final_event_reconciles_authoritative_timeout_without_retry():
    controller,api=running()
    api.get_session=Mock(return_value={'status':'timed_out'})
    controller.process_next_event=Mock(side_effect=AssertionError('Terminal confirmation must end the event loop'))
    controller._run_loop(None)
    state=controller.status()
    assert state['status']=='timed_out' and state['run_ended_at'] is not None
    assert controller._stop_event.is_set()
    assert state['provider'] is None
    assert 'runtime limit' in state['error']
    api.stop_session.assert_not_called()
    controller.process_next_event.assert_not_called()


def test_time_or_failed_confirmation_never_fabricates_completion():
    controller,api=running()
    api.get_session=Mock(return_value={'status':'running'})
    controller._run_started_at=time.time()
    assert controller._reconcile_expired_session() is False
    api.get_session.assert_not_called()
    controller._run_started_at=time.time()-61
    assert controller._reconcile_expired_session() is False
    assert controller.status()['status']=='running'
    controller._next_terminal_check=0
    api.get_session.side_effect=TimeoutError('No authoritative response')
    assert controller._reconcile_expired_session() is False
    assert controller.status()['status']=='running'
    api.stop_session.assert_not_called()
    controller.disconnect()


def test_delayed_confirmation_cannot_overwrite_a_new_session():
    controller,api=running()
    def late_response(session_id):
        controller._session_id='new-session'
        return {'status':'timed_out'}
    api.get_session=late_response
    assert controller._reconcile_expired_session() is False
    assert controller.status()['session_id']=='new-session'
    assert controller.status()['status']=='running'
    api.stop_session.assert_not_called()
    controller._session_id=None
    controller.disconnect()
