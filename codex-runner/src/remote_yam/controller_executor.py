"""Runner control for installed controller policies; inference stays on the robot."""
import time
import uuid
from .session import SessionAPIError

ROBOHOUSE = 'robot-ba8413962083809c'
DREAM_MODEL = 'dreamlabs/dream-1-beta'


def selected_executor(executor, *, provider, model, robot_id, models=None, model_id=None, custom_endpoint=None):
    """Omitted/null routing preserves the existing provider instance and wire flow."""
    if executor is None:
        if model_id is not None or custom_endpoint is not None:
            raise ValueError('Controller model selection requires controller execution')
        return None
    if executor == 'controller':
        from .controller_models import ROBOTS, public_models, registration_id
        if robot_id not in ROBOTS:
            raise ValueError('Controller model execution requires a supported YAM controller')
        spec = public_models(models or {}).get(registration_id(model_id))
        if not spec or not spec['available']:
            raise ValueError('Controller model is not provisioned on this robot')
        if spec.get('user_endpoint'):
            from .model_catalog import model_id as validate_model
            from .controller_custom import validate_custom
            model, custom_endpoint = validate_model(model), validate_custom(custom_endpoint)
        elif custom_endpoint is not None:
            raise ValueError('This predefined controller model does not accept an endpoint override')
        elif model not in ('', spec['model']):
            raise ValueError('Provider/model differs from the selected controller registration')
        if provider != spec['provider']:
            raise ValueError('Provider/model differs from the selected controller registration')
        return ControllerExecutorPolicy(provider=provider, model=model or spec['model'], executor=executor,
                                        model_id=model_id, label=spec['label'], custom_endpoint=custom_endpoint)
    if executor != 'dream_one' or not isinstance(executor, str):
        raise ValueError('Unknown controller executor')
    if provider != 'dream' or model not in ('', DREAM_MODEL):
        raise ValueError('dream_one requires Dream-1 beta')
    if robot_id != ROBOHOUSE:
        raise ValueError('Dream controller execution is installed only on RoboHouse YAM')
    return ControllerExecutorPolicy()


def execution_request(api, context, executor, operation='start', *, request_id=None, model_id=None, custom_endpoint=None, model=None):
    if executor is None:
        return None
    if executor not in {'dream_one', 'controller'} or operation not in {'start', 'predict', 'status'}:
        raise ValueError('Unsupported controller executor or operation')
    selection = {}
    if executor == 'controller':
        from .controller_models import registration_id
        selection = {'model_id': registration_id(model_id)}
        if custom_endpoint is not None:
            from .controller_custom import validate_custom
            from .model_catalog import model_id as validate_model
            selection.update(custom_endpoint=validate_custom(custom_endpoint), model=validate_model(model))
    session_id = context['session_id']
    payload = dict(schema_version=1, executor=executor, operation=operation, payload=selection,
        request_id=request_id or uuid.uuid4().hex,
        **{key: context[key] for key in ('episode_id', 'lease_id')})
    return api._request('POST', '/v1/sessions/' + session_id + '/executions', payload,
                        bearer=api._capability(session_id))


class ControllerExecutorPolicy:
    provider_name = 'dream'
    model = DREAM_MODEL
    share_conversation = False
    interaction_sink = None

    def __init__(self, *, provider='dream', model=DREAM_MODEL, executor='dream_one', model_id=None, label='Dream', custom_endpoint=None):
        self.provider_name, self.model = provider, model
        self.executor, self.model_id, self.label = executor, model_id, label
        self.custom_endpoint = custom_endpoint

    def public_config(self):
        return dict(provider=self.provider_name, model=self.model, executor=self.executor,
                    execution_location='controller', cadence_hz=10,
                    display_name=self.label,
                    **({'controller_model': self.model_id} if self.model_id else {}))

    def configure_run_duration(self, seconds):
        self.duration = seconds

    def run_session(self, prompt, observation, api, context, cancelled):
        def request(operation):
            if cancelled():
                return {'state': 'cancelled'}
            try:
                response = execution_request(api, context, self.executor, operation, model_id=self.model_id,
                    custom_endpoint=self.custom_endpoint, model=self.model)
                while response['status'] == 'pending':
                    if cancelled():
                        return {'state': 'cancelled'}
                    time.sleep(.1)
                    response = api._request('GET', '/v1/sessions/' + context['session_id']
                        + '/executions/' + response['request_id'], bearer=api._capability(context['session_id']))
            except SessionAPIError:
                if cancelled():  # A request can cross the selected-duration deadline.
                    return {'state': 'cancelled'}
                raise
            if cancelled():
                return {'state': 'cancelled'}
            if response['status'] != 'completed':
                raise RuntimeError('Controller ' + self.label + ' execution request failed')
            return response['result']
        state = request('start')
        previous = None
        while not cancelled():
            phase = state.get('state')
            if phase != previous and self.interaction_sink:
                self.interaction_sink('model_progress', 'Controller ' + self.label + ': ' + str(phase))
            previous = phase
            if phase in {'completed', 'cancelled'}:
                return state
            if phase == 'failed':
                raise RuntimeError('Controller ' + self.label + ' execution failed')
            time.sleep(.25)
            state = request('status')
        return {'state': 'cancelled'}
