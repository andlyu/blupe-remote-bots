"""Validate follower tracking geometry separately from command velocity."""
import math


TRACKING_LIMIT_RAD = math.radians(45)


def check_tracking_error(measured, target):
    measured, target = tuple(measured), tuple(target)
    if len(measured) != 12 or len(target) != 12 or not all(
            math.isfinite(v) for v in measured + target):
        raise ValueError('Invalid tracking positions')
    errors = tuple(abs(a-b) for a,b in zip(measured,target))
    index = max(range(12), key=errors.__getitem__)
    distance = errors[index]
    if distance > TRACKING_LIMIT_RAD:
        side = 'left' if index < 6 else 'right'
        raise ValueError(f'Follower tracking error: {side} joint {index % 6 + 1}; '
                         f'measured={measured[index]:.4f} rad, target={target[index]:.4f} rad, '
                         f'error={distance:.4f} rad > {TRACKING_LIMIT_RAD:.4f} rad; teleop disengaged')
    return distance


def check_tracking_sweep(guard, config, measured, target):
    measured, target = tuple(measured), tuple(target)
    distance = check_tracking_error(measured, target)
    count = max(1, math.ceil(distance/config.sweep_resolution_rad))
    # These are geometric samples, not a timed command trajectory. Command
    # velocity is checked on previous-command -> next-command independently.
    for index in range(count+1):
        alpha=index/count
        pose=tuple(a+(b-a)*alpha for a,b in zip(measured,target))
        guard.approve(pose,(pose,),cadence_hz=10,target_limit_tolerance_rad=.005)
