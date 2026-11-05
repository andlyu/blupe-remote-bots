"""Verify actual DreamAdapter encoded observations without inference or motors."""
import base64
import asyncio
import io
import json
import os
from pathlib import Path
import sys
import time

import pytest
from PIL import Image, ImageStat

from brightness import (BrightnessCameraSource, brightness_factor, configure_policy,
                        preview_jpeg, transform_image, transformed_frame)
from serve import make_runner_type, runner_root

ROOT = runner_root(os.environ.get('YAM_DREAM_RUNNER_ROOT'))
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from remote_yam.cameras import CameraFrame
from remote_yam.dream_policy import DreamAdapter


def frames():
    result = []
    for name, color in [('top', (200, 120, 80)), ('left', (100, 180, 220)), ('right', (240, 160, 120))]:
        output = io.BytesIO()
        Image.new('RGB', (640, 360), color).save(output, format='JPEG', quality=90)
        result.append(CameraFrame(name, output.getvalue(), time.time(),
                                  source_captured_at=time.time(), view={'source': name}))
    return result


@pytest.mark.parametrize('value', [-.1, 2.01, float('nan'), float('inf'), True, False, '0.5', None])
def test_invalid_brightness_rejected(value):
    with pytest.raises(ValueError):
        brightness_factor(value)


def test_exact_rgb_scaling_and_extremes():
    output = io.BytesIO()
    Image.new('RGB', (1, 1), (201, 120, 81)).save(output, format='PNG')
    assert transform_image(output.getvalue(), .5).getpixel((0, 0)) == (100, 60, 40)
    assert transform_image(output.getvalue(), 0).getpixel((0, 0)) == (0, 0, 0)
    assert transform_image(output.getvalue(), 2).getpixel((0, 0)) == (255, 240, 162)


def test_metadata_and_lossless_intermediate():
    original = frames()[0]
    assert transformed_frame(original, 1) is original
    modified = transformed_frame(original, .5)
    assert modified.jpeg.startswith(b'\x89PNG')
    assert (modified.name, modified.received_at, modified.source_captured_at, modified.view) == (
        original.name, original.received_at, original.source_captured_at, original.view)


def test_actual_adapter_encoded_inputs_match_preview_and_half_brightness(tmp_path):
    original = frames()
    class Cameras:
        def capture_for_policy(self, observation, **kwargs):
            assert callable(kwargs['cancelled'])
            assert callable(kwargs['on_event'])
            return original

    def observation():
        return dict(jetson_id='yam-1', observed_at=time.time(), left_joints_deg=[10.] * 6,
                    right_joints_deg=[20.] * 6, left_gripper=.3, right_gripper=.7)

    ticks = {}
    for factor in (1, .5, 0, 2):
        provider = DreamAdapter(provider='dream', model='dreamlabs/dream-1-beta',
            credentials='unused', python='unused', directory=tmp_path,
            camera_source=Cameras(), observation_source=observation, robot_id='yam-1')
        configure_policy(provider, factor)
        ticks[factor] = provider._capture_tick()
        assert provider.public_config()['image_experiment']['brightness_factor'] == factor
        assert provider.public_config()['model'] == 'dreamlabs/dream-1-beta'
        mapping = {'top':'overhead', 'left':'wrist_l', 'right':'wrist_r'}
        assert set(ticks[factor]['frames']) == {'video.' + role for role in mapping.values()}
        for frame in original:
            encoded = base64.b64decode(ticks[factor]['frames']['video.' + mapping[frame.name]])
            assert encoded == preview_jpeg(frame, factor)
            with Image.open(io.BytesIO(encoded)) as image:
                assert image.size == (320, 176)
                assert image.format == 'JPEG'
    for key in ticks[1]['frames']:
        def means(factor):
            return ImageStat.Stat(Image.open(io.BytesIO(base64.b64decode(ticks[factor]['frames'][key])))).mean
        assert all(abs(dark - normal * .5) <= 2 for dark, normal in zip(means(.5), means(1)))
        assert means(0) == [0, 0, 0]
    assert ticks[.5]['observation']['state.left_gripper'] == [.3]
    assert ticks[.5]['observation']['state.right_gripper'] == [.7]


def test_launch_rejects_bad_factor_before_queue(tmp_path):
    runner_type = make_runner_type(ROOT)
    runner = runner_type.__new__(runner_type)
    from playground import RequestError
    with pytest.raises(RequestError, match='brightness'):
        runner.launch(None, {'provider':'dream', 'image_brightness':-1})
    with pytest.raises(RequestError, match='Dream1'):
        runner.launch(None, {'provider':'codex', 'image_brightness':.5})


def test_preview_uses_existing_camera_source_and_matches_policy_encoding():
    runner_type = make_runner_type(ROOT)
    runner = runner_type.__new__(runner_type)
    runner.robot_id = 'yam-1'
    runner.secure = False
    original = frames()
    class Monitor:
        def get_robot_observation(self, robot):
            assert robot == 'yam-1'
            return {'observation': {'images': 'unused'}}
    class Cameras:
        # Deliberately no origin URL: the configured source already validates it.
        def capture(self, observation):
            return original
    runner.monitor_api = Monitor()
    runner.camera_source = Cameras()
    replies = []
    async def send(message):
        replies.append(message)
    result = asyncio.run(runner.public_extension(
        {'method':'GET', 'path':'/experiment/preview', 'query_string':b'brightness=0.5'},
        None, send, {}))
    assert result is True
    assert replies[0]['status'] == 200
    payload = json.loads(replies[1]['body'])
    assert payload['brightness_factor'] == .5
    assert len(payload['frames']) == 3
    for frame, encoded in zip(original, payload['frames']):
        assert base64.b64decode(encoded['jpeg']) == preview_jpeg(frame, .5)


@pytest.mark.parametrize('payload', [
    {}, {'runner_name':'Local runner','email':'person@example.com'},
    {'runner_name':'Researcher'}, {'runner_name':False,'email':'person@example.com'}])
def test_identity_is_collected_before_launch(payload):
    runner_type = make_runner_type(ROOT)
    runner = runner_type.__new__(runner_type)
    from playground import RequestError
    with pytest.raises(RequestError):
        runner.validate_launch(None, payload, False)


def test_public_session_never_reads_private_local_identity(tmp_path, monkeypatch):
    from local_playground import LocalPlayground
    from playground import RequestError
    async def base_session(self, cookies, visitor):
        return {}, []
    monkeypatch.setattr(LocalPlayground, 'session_extension', base_session)
    runner_type = make_runner_type(ROOT, local=False)
    runner = runner_type.__new__(runner_type)
    monkeypatch.setenv('YAM_BRIGHTNESS_IDENTITY_FILE', str(tmp_path / 'must-not-be-read.json'))
    with pytest.raises(RequestError, match='restricted to the local'):
        asyncio.run(runner.session_extension({}, None))
    monkeypatch.delenv('YAM_BRIGHTNESS_IDENTITY_FILE')
    data, headers = asyncio.run(runner.session_extension({}, None))
    assert data['runner_identity'] == {} and data['local_runner'] is False
    assert data['default_provider'] == 'dream' and headers == []
