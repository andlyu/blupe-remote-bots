"""The active immutable replay-cache adapter must report encoded pacing."""
import hashlib
import json

import pytest
from remote_yam.quick_replays import QuickReplays


@pytest.mark.parametrize('metadata,expected',[({},10),({'speed':2},2),({'speed':10},10),
    ({'nominal_action_speed':2},2),({'speed':2,'nominal_action_speed':10},2),
    ({'speed':True},None),({'speed':float('nan')},None),({'speed':20},None)])
def test_encoded_pacing_keeps_identity_range_and_quality_stage(tmp_path,metadata,expected):
    body=b'synthetic video';digest=hashlib.sha256(body).hexdigest()
    (tmp_path/'ep_fixture').mkdir();(tmp_path/'ep_fixture'/(digest+'.mp4')).write_bytes(body)
    info=dict(sha256=digest,duration_s=1,camera_order=['observer'],quality_stage='quick',**metadata)
    (tmp_path/'ep_fixture.json').write_text(json.dumps(dict(episode_id='ep_fixture',robot_id='fixture',
        bytes=len(body),preview=info,locally_ready_at=1)))
    source=QuickReplays(tmp_path)
    result=source.get('ep_fixture','fixture')
    if expected is None:
        assert result is None
    else:
        assert result['preview_speed']==expected and result['video_quality']=='quick'
        assert result['video_sha256']==digest and source.get('ep_fixture','other') is None
        assert source.video('ep_fixture',digest,'bytes=0-3')[:2]==(206,body[:4])
