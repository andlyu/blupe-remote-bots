"""Validate an opt-in replay request for the operator's queue notification."""
from .socials import social_handles


def recipient(payload):
    enabled = payload.get('email_run_video', False)
    if type(enabled) is not bool:
        raise ValueError('Run video email must be true or false')
    if not enabled:
        return ''
    email = social_handles(payload)['email']
    if not email:
        raise ValueError('Enter a valid email address to request your run video')
    return email
