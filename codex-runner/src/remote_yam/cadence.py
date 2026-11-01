"""Supported waypoint clocks; independent of model inference and motor loops."""
import math

DEFAULT_CADENCE_HZ = 10.0
SUPPORTED_CADENCES_HZ = (10.0, 20.0, 30.0)


def trajectory_cadence(value=DEFAULT_CADENCE_HZ):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value not in SUPPORTED_CADENCES_HZ):
        raise ValueError('cadence_hz must be 10, 20 or 30')
    return float(value)
