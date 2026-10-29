"""Runner control for installed controller policies; inference stays on the robot."""
import time
import uuid

ROBOHOUSE = 'robot-ba8413962083809c'
DREAM_MODEL = 'dreamlabs/dream-1-beta'


def selected_executor(executor, *, provider, model, robot_id):
    """Omitted/null routing preserves the existing provider instance and wire flow."""
    if executor is None:
        return None
    if executor != 'dream_one' or not isinstance(executor, str):
        raise ValueError('Unknown controller executor')
    if provider != 'dream' or model not in ('', DREAM_MODEL):
        raise ValueError('dream_one requires Dream-1 beta')
    if robot_id != ROBOHOUSE:
        raise ValueError('Dream controller execution is installed only on RoboHouse YAM')
    return ControllerExecutorPolicy()


def execution_request(api, context, executor, operation='start', *, request_id=None):
    if executor is None:
        return None
    if executor != 'dream_one' or operation not in {'start', 'predict', 'status'}:
        raise ValueError('Unsupported controller executor or operation')
    session_id = context['session_id']
    payload = dict(schema_version=1, executor=executor, operation=operation, payload={},
        request_id=request_id or uuid.uuid4().hex,
        **{key: context[key] for key in ('episode_id', 'lease_id')})
    return api._request('POST', '/v1/sessions/' + session_id + '/executions', payload,
                        bearer=api._capability(session_id))


class ControllerExecutorPolicy:
    provider_name = 'dream'
    model = DREAM_MODEL
    share_conversation = False
    interaction_sink = None

    def public_config(self):
        return dict(provider='dream', model=self.model, executor='dream_one',
                    execution_location='controller', cadence_hz=10)

    def configure_run_duration(self, seconds):
        self.duration = seconds

    def run_session(self, prompt, observation, api, context, cancelled):
        def request(operation):
            if cancelled():
                return {'state': 'cancelled'}
            response = execution_request(api, context, 'dream_one', operation)
            while response['status'] == 'pending':
                if cancelled():
                    return {'state': 'cancelled'}
                time.sleep(.1)
                response = api._request('GET', '/v1/sessions/' + context['session_id']
                    + '/executions/' + response['request_id'], bearer=api._capability(context['session_id']))
            if response['status'] != 'completed':
                raise RuntimeError('Controller Dream execution request failed')
            return response['result']
        state = request('start')
        previous = None
        while not cancelled():
            phase = state.get('state')
            if phase != previous and self.interaction_sink:
                self.interaction_sink('model_progress', 'Controller Dream: ' + str(phase))
            previous = phase
            if phase in {'completed', 'cancelled'}:
                return state
            if phase == 'failed':
                raise RuntimeError('Controller Dream execution failed')
            time.sleep(.25)
            state = request('status')
        return {'state': 'cancelled'}
