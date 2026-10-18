"""Recorded replay identities; recording content is supplied by the station."""
import re

def episode_name(value):
    if not isinstance(value,str) or not re.fullmatch(r'physical-[0-9]+',value):
        raise ValueError('Invalid episode ID')
    return value
