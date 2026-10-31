"""YAM1-only policy boundary. No robot IO or model imports.

Checkpoint: allenai/MolmoAct2-BimanualYAM@8dcbed66f2380e4393189c303ea72488eb9e63c2.
Camera order and raw state/action scales follow its pinned model card.
"""
import base64
import math

MODEL = 'allenai/MolmoAct2-BimanualYAM'
REVISION = '8dcbed66f2380e4393189c303ea72488eb9e63c2'
ROBOT_ID = 'yam-1'
CAMERAS = ('top', 'left', 'right')
GRIPPER_UNITS = 'normalized_0_closed_1_open'
NORM_TAG = 'yam_dual_molmoact2'
ACTION_DIM = 14
NUM_ACTIONS = 30
MAX_BODY = 8 * 1024 * 1024


def finite_vector(value, length):
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f'Expected {length} numeric values')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ValueError('Non-finite or non-numeric values')
    return [float(x) for x in value]


def valid_grippers(value):
    if any(not 0.0 <= value[index] <= 1.0 for index in (6, 13)):
        raise ValueError('Gripper values must be normalized in [0, 1]')


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get('robot_id') != ROBOT_ID:
        raise ValueError('This checkpoint supports only robot_id yam-1')
    if payload.get('action_units') != 'radians':
        raise ValueError('YAM1 arm joints must use radians')
    if payload.get('gripper_units') != GRIPPER_UNITS:
        raise ValueError('Explicit normalized_0_closed_1_open gripper units are required')
    instruction = payload.get('instruction')
    if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 4096:
        raise ValueError('A nonempty instruction of at most 4096 characters is required')
    state = finite_vector(payload.get('state'), ACTION_DIM)
    valid_grippers(state)
    images = payload.get('images')
    if not isinstance(images, dict) or set(images) != set(CAMERAS):
        raise ValueError('Exactly top, left, right camera JPEGs are required')
    decoded = []
    for camera in CAMERAS:
        data = images[camera]
        if not isinstance(data, str) or not 0 < len(data) <= MAX_BODY:
            raise ValueError(f'Invalid {camera} JPEG')
        try:
            decoded.append(base64.b64decode(data, validate=True))
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError(f'Invalid {camera} JPEG base64') from exc
    return instruction.strip(), state, decoded


def validate_actions(actions):
    if not isinstance(actions, (list, tuple)) or len(actions) != NUM_ACTIONS:
        raise ValueError(f'Expected {NUM_ACTIONS} actions')
    result = []
    for row in actions:
        values = finite_vector(row, ACTION_DIM)
        valid_grippers(values)
        result.append(values)
    return result


def identity():
    return dict(robot_id=ROBOT_ID, model=MODEL, revision=REVISION,
                action_units='radians', gripper_units=GRIPPER_UNITS,
                action_dim=ACTION_DIM, num_actions=NUM_ACTIONS, norm_tag=NORM_TAG)
