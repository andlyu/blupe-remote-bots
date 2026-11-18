"""Google DeviceLayer commands to endpoint-exact canonical YAM packets.

The native RunnerController owns the lease, Home, dispatch, measured feedback
and Stop. This compiler owns no transport, CAN connection, key or robot.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from remote_yam.session import MAX_COMMANDS, MAX_WAYPOINTS_PER_PACKET, _trajectory_waypoints

ARMS = ('left', 'right')
CADENCE_HZ = 10
SAFETY_SHA256 = '9a305c10a44e1093ebd21d138e992443263edb8dc5c06c3004c62371f2d3c69f'
KEYS = {f'{arm}/follower/goal_position/{joint}': (arm, index)
        for arm in ARMS for index, joint in enumerate([*[f'joint{i}' for i in range(1, 7)], 'gripper'])}


class CommandRejected(ValueError):
    stage = 'local_validation'
    dispatched = False


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CommandRejected('Duplicate command field; no motion sent')
        result[key] = value
    return result


def number(value, field):
    if type(value) not in (int, float):
        raise CommandRejected(f'{field} requires a finite JSON number; no motion sent')
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise CommandRejected(f'{field} requires a finite JSON number; no motion sent')
    return float(value)


def wire_degrees(radians, low, high):
    """Choose a representable degree value without expanding native bounds.

    A valid radian endpoint can round one ULP outward during the wire's
    radian→degree→radian conversion. Move that encoded degree value one ULP
    inward only after validating the requested radian value. Invalid input
    never reaches this adjustment; all native bounds remain strict.
    """
    if not low <= radians <= high:
        raise CommandRejected('Generated joint point exceeds native limits; no motion sent')
    encoded = math.degrees(radians)
    decoded = math.radians(encoded)
    if decoded < low:
        encoded = math.nextafter(encoded, math.inf)
    elif decoded > high:
        encoded = math.nextafter(encoded, -math.inf)
    if not low <= math.radians(encoded) <= high:
        raise CommandRejected('Joint endpoint is not representable on the wire; no motion sent')
    return encoded


class YamCommands:
    def __init__(self, runner_root):
        path = Path(runner_root) / 'config/controller-workspaces/native-both-20260929.safety.json'
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != SAFETY_SHA256:
            raise CommandRejected('Canonical YAM1 safety snapshot changed; no motion sent')
        self.safety = json.loads(data)

    @staticmethod
    def parse(raw):
        if isinstance(raw, str):
            if len(raw.encode()) > 16000:
                raise CommandRejected('Command is too large; no motion sent')
            try:
                raw = json.loads(raw, object_pairs_hook=unique_fields)
            except ValueError as exc:
                raise CommandRejected('Command must be JSON; no motion sent') from exc
        if not isinstance(raw, dict) or set(raw) != {'commands', 'duration_s'}:
            raise CommandRejected('Expected commands and duration_s; no motion sent')
        commands = raw['commands']
        if not isinstance(commands, dict) or not commands or set(commands) - set(KEYS):
            raise CommandRejected('Use the registered left/right DeviceLayer goal keys; no motion sent')
        duration = number(raw['duration_s'], 'duration_s')
        if duration <= 0:
            raise CommandRejected('duration_s must be positive; no motion sent')
        return {key: number(value, key) for key, value in commands.items()}, duration

    def compile(self, raw, observation, first_step_id):
        commands, duration = self.parse(raw)
        if type(first_step_id) is not int or not 0 <= first_step_id < MAX_COMMANDS:
            raise CommandRejected('Invalid or exhausted command cursor; no motion sent')
        if duration > MAX_WAYPOINTS_PER_PACKET / CADENCE_HZ:
            raise CommandRejected('Command exceeds the existing packet budget; no motion sent')
        if not isinstance(observation, dict):
            raise CommandRejected('Measured bimanual feedback is required; no motion sent')
        count = math.ceil(duration * CADENCE_HZ)
        if count > MAX_WAYPOINTS_PER_PACKET or first_step_id + count > MAX_COMMANDS:
            raise CommandRejected('Command exceeds the existing packet/session budget; no motion sent')
        starts, targets = {}, {}
        for arm in ARMS:
            joints = observation.get(arm + '_joints_deg')
            if not isinstance(joints, (list, tuple)) or len(joints) != 6:
                raise CommandRejected(f'{arm} requires six measured joints; no motion sent')
            starts[arm] = [math.radians(number(v, arm + '_joints_deg')) for v in joints]
            grip = number(observation.get(arm + '_gripper'), arm + '_gripper')
            if not 0 <= grip <= 1:
                raise CommandRejected(f'{arm} measured gripper must be in [0,1]; no motion sent')
            starts[arm].append(grip)
            targets[arm] = starts[arm].copy()
        for key, target in commands.items():
            arm, index = KEYS[key]
            if index == 6 and not 0 <= target <= 1:
                raise CommandRejected(f'{key}={target!r} must be in [0,1]; no motion sent')
            targets[arm][index] = target
        max_step = min(self.safety['max_adjacent_delta_rad'], self.safety['max_joint_velocity_rad_s'] / CADENCE_HZ)
        for arm_index, arm in enumerate(ARMS):
            for joint, target in enumerate(targets[arm][:6]):
                index = arm_index * 6 + joint
                if not self.safety['joint_lower_rad'][index] <= target <= self.safety['joint_upper_rad'][index]:
                    raise CommandRejected(f'{arm} joint{joint+1} target is outside native limits; no motion sent')
                if abs(target - starts[arm][joint]) / count > max_step:
                    raise CommandRejected(f'{arm} joint{joint+1} duration exceeds native speed limits; no motion sent')
        points = []
        for step in range(1, count + 1):
            point = {'step_id': first_step_id + step - 1}
            for arm in ARMS:
                point[arm + '_joints_deg'] = deepcopy(list(observation[arm + '_joints_deg']))
                point[arm + '_gripper'] = observation[arm + '_gripper']
                for key, (side, index) in KEYS.items():
                    if side != arm or key not in commands:
                        continue
                    # Reuse exact validated endpoints, including close=0.
                    value = targets[arm][index] if step == count else starts[arm][index] + (targets[arm][index] - starts[arm][index]) * (step / count)
                    if index == 6:
                        point[arm + '_gripper'] = value
                    else:
                        native = ARMS.index(arm) * 6 + index
                        point[arm + '_joints_deg'][index] = wire_degrees(value, self.safety['joint_lower_rad'][native], self.safety['joint_upper_rad'][native])
            points.append(point)
        # Real client validator, also called by HttpSessionAPI serialization.
        return _trajectory_waypoints(points)
