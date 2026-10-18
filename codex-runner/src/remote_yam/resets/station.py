"""Explicit deployment resources for portable reset code; no station defaults."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_RESOURCES=ContextVar('reset_station_resources',default={})


def configure(resources):
    """Set resources for an owning integration's current context."""
    return _RESOURCES.set(dict(resources))


@contextmanager
def configured(resources):
    token=configure(resources)
    try:yield
    finally:_RESOURCES.reset(token)


def resource(name):
    resources=_RESOURCES.get()
    if name in resources:return resources[name]
    if name=='auditor':return Path(__file__).with_name('installed_geometry.py')
    raise ValueError('Reset station configuration is missing: '+name)
