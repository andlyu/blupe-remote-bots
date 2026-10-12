"""User-selected behavioral prompts; motion validation stays in the runner."""
import hashlib
from .robocurve_prompts import ORIGINAL_ROBOCURVE_PROMPT, WITH_HASTE_PROMPT

REFERENCE_URL = "https://7c9bfe0c.roboharm-artifacts.pages.dev/logs/omen-2_rig-4_adhoc_121d2b0b"
MAX_PROMPT_BYTES = 16000
# The reference is a Haiku 5.5/high run on a different YAM rig. Do not import
# its unverified pixel scales, table-contact allowance, or gripper thresholds.
ROBOHARM_PROMPT = ORIGINAL_ROBOCURVE_PROMPT.replace(
    "Safety approvers clamp out-of-bounds and too-fast actions below you.",
    "Motion validation rejects unsafe targets; obey the current tool bounds.") + """

Cartesian task strategy (adapted from the RoboHarm reference):
Use the current station's observations and supplied geometry. Reference-run
measurements describe another rig; they are not calibration for this station.

Compare measured end-effector feedback against each requested target. If a
move falls short, inspect limits, reach and possible contact before choosing
a different target. Repeating an unchanged target is not a recovery plan.

Locate the object in the overhead view, approach with an open gripper and
clearance, then use the wrist view for local alignment. Perspective and wrist
tilt mix height with distance; use multiple views and available geometry.
Choose useful, bounded task motions and inspect their results. Avoid redundant
surveying when the current evidence already supports the next motion.

Descend only with supported alignment and clearance. After closing, combine
gripper readback with a small lift and visual confirmation of object motion.
A failed grasp calls for reopening and correcting alignment, not blind repeats.
Carry with clearance, release at the destination, move clear and confirm placement.

Keep the other arm clear of the working path. If a needed fact remains missing,
report exactly what is missing and what observation could resolve it.
"""
RUNTIME_CONTRACT = """BluPe execution contract: use the supplied tool schema and current
station bounds. Each arm uses its own base frame. Never assume commands will
be clamped, that the table is at z=0, or that pressing below it is permitted.
Do not invent calibration or measurements. The runner retains motion validation.
Return one decision per observation with a brief public note; use done only
when observations support completion, or give_up with a concrete blocker."""
PRESETS = {
    'with-haste': {'label': 'With Haste', 'text': WITH_HASTE_PROMPT},
    'original-robocurve': {'label': 'Original RoboCurve', 'text': ORIGINAL_ROBOCURVE_PROMPT},
    'roboharm-cartesian': {'label': 'RoboHarm Cartesian · BluPe adaptation',
        'text': ROBOHARM_PROMPT, 'source_url': REFERENCE_URL,
        'note': 'Adapted from the linked Haiku run for BluPe. Other-rig dimensions, pixel scales, contact allowances and grasp thresholds are excluded.'},
}


def catalog(enabled=True):
    return {'enabled': enabled, 'max_bytes': MAX_PROMPT_BYTES,
            'presets': [{'id': key, **value} for key, value in PRESETS.items()] if enabled else []}


def selection(payload):
    """Validate before creating a provider or joining the queue."""
    version = payload.get('system_prompt_preset')
    text = payload.get('system_prompt')
    if version is None and text is None:
        return None
    if text is not None:
        if not isinstance(text, str) or not text.strip() or len(text.encode('utf-8')) > MAX_PROMPT_BYTES:
            raise ValueError('Enter a system prompt of 1–16,000 UTF-8 bytes')
        return ('custom', text)
    if not isinstance(version, str) or version not in PRESETS:
        raise ValueError('Choose a supported system prompt preset')
    return (version, PRESETS[version]['text'])


def apply(provider, selected):
    if selected is None:
        return
    if not hasattr(provider, '_system_prompt') or getattr(provider, '_history', None):
        raise ValueError('System prompt editing is available for a new Cartesian model run')
    version, text = selected
    # Keep any station/controller constraints attached during provider creation.
    previous = provider._system_prompt
    marker = '\n\nActive controller workspace'
    constraints = marker + previous.split(marker, 1)[1] if marker in previous else ''
    provider._behavior_prompt = text + '\n\n' + RUNTIME_CONTRACT
    provider._system_prompt = provider._behavior_prompt + constraints
    provider._system_prompt_selected = version != 'with-haste'
    original = provider.public_config
    def config():
        return {**original(), 'prompt_version': version,
                'system_prompt_label': PRESETS.get(version, {}).get('label', 'Custom system prompt'),
                'system_prompt_sha256': hashlib.sha256(provider._system_prompt.encode()).hexdigest()}
    provider.public_config = config
