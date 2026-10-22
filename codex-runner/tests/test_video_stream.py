import json
import unittest
from unittest.mock import patch
from remote_yam.video_stream import video_stream

class VideoConfigTests(unittest.TestCase):
    def test_robohouse_default_has_the_verified_four_view_slot_order(self):
        with patch.dict('os.environ', {'YAM_VIDEO_STREAMS': '{}'}):
            self.assertEqual(video_stream('robot-ba8413962083809c'), {
                'path': 'robo-house', 'cameras': ['top', 'left', 'right', 'observer']})

    def test_robohouse_explicit_legacy_layout_and_disabled_stream_are_preserved(self):
        robot = 'robot-ba8413962083809c'
        legacy = {'path': 'robo-house', 'cameras': ['top', 'left', 'right']}
        for value in [legacy, None]:
            with patch.dict('os.environ', {'YAM_VIDEO_STREAMS': json.dumps({robot: value})}):
                self.assertEqual(video_stream(robot), value)

    def test_defaults_and_independent_robot_override(self):
        with patch.dict('os.environ', {'YAM_VIDEO_STREAMS': json.dumps({'robo': {'path':'robo-house','cameras':['top','left','right']}})}):
            self.assertEqual(video_stream('yam-1')['path'], 'synchronized-hd')
            self.assertEqual(video_stream('robo'), {'path':'robo-house','cameras':['top','left','right']})
            self.assertIsNone(video_stream('so101'))
    def test_invalid_paths_and_tile_roles_fail_before_serving(self):
        invalid = [dict(path='../private',cameras=['top']), dict(path='https://elsewhere',cameras=['top']),
                   dict(path='valid',cameras=['top','top']), dict(path='valid',cameras=[]),
                   dict(path='valid',cameras=['secret']), dict(path='valid',cameras='top')]
        for value in invalid:
            with self.subTest(value=value), patch.dict('os.environ',{'YAM_VIDEO_STREAMS':json.dumps({'robo':value})}):
                with self.assertRaises(ValueError):video_stream('robo')

    def test_legacy_stream_remains_an_explicit_override(self):
        legacy = {'path':'synchronized','cameras':['top','observer','left','right']}
        with patch.dict('os.environ', {'YAM_VIDEO_STREAMS':json.dumps({'yam-1':legacy})}):
            self.assertEqual(video_stream('yam-1'), legacy)
