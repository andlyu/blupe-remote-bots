"""Server-configured policy defaults; explicit launch choices stay authoritative."""


def default_run_duration(spec):
    seconds = spec.get('default_run_duration_s', 300)
    if type(seconds) is not int or not 60 <= seconds <= 600 or seconds % 60:
        raise ValueError('Configured default duration must be whole minutes from 1 to 10')
    return seconds
