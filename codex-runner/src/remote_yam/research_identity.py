"""Confirmed research-run identity; contact addresses remain private."""
from .socials import social_handles


def research_runner(payload):
    kind = payload.get('runner_kind', 'human')
    if kind == 'automated':
        if payload.get('email', '').strip():
            raise ValueError('Automated runs must not supply a human email')
        return dict(name='Automated CAG test', kind='automated', email_confirmed=False)
    if kind != 'human':
        raise ValueError('Choose a human or automated runner')
    name = payload.get('runner_name', '')
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 32
            or any(ord(c) < 32 for c in name)
            or name.strip().casefold() in ('anonymous', 'local runner')):
        raise ValueError('Confirm your name before joining')
    if not social_handles(payload)['email']:
        raise ValueError('Confirm your email before joining')
    return dict(name=name.strip(), kind='human', email_confirmed=True)
