import json

from remote_yam.past_runs import PastRuns


def test_saved_preview_layout_reaches_player_from_archive_and_viewing_index():
    preview = dict(speed=10, layout='observer-focus', camera_order=['observer', 'left', 'top', 'right'])
    for use_index in (False, True):
        catalog = PastRuns(lambda _: json.dumps({} if use_index else dict(preview=preview)))
        if use_index:
            catalog.viewing['ep_layout'] = dict(preview=preview)
        _, detail = catalog._detail(dict(episode_id='ep_layout'))
        assert detail['video_layout'] == 'observer-focus'
        assert detail['camera_order'] == preview['camera_order']


def test_legacy_layout_remains_unspecified():
    _, detail = PastRuns(lambda _: '{}')._detail(dict(episode_id='ep_legacy'))
    assert detail['video_layout'] is None
