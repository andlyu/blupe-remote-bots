import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
import playground
from remote_yam.groot_policy import GrootAdapter
from remote_yam.session import MockSessionAPI


CONFIG = {'model': 'groot-northstar-purple-crate-step10000', 'label': 'GR00T · NorthStar',
          'robot_ids': ['robohouse'], 'endpoint': 'https://testendpoint.api.runpod.ai',
          'norm_tag': 'yam_northstar_purple_crate', 'artifact_sha256': 'a' * 64}


@pytest.mark.parametrize('robot,hardware,enabled', [('robohouse','yam',True), ('yam-1','yam',False), ('robohouse','custom',False)])
def test_server_configuration_scopes_model_to_robot(robot, hardware, enabled):
    app = playground.HostedRunner(public_origin='https://robot.example', session_api='https://session.example',
        camera_origin='https://session.example', robot_id=robot, hardware=hardware,
        groot_key_file='/unused', groot_config=CONFIG,
        api_factory=lambda: MockSessionAPI(auto_activate=False))
    try:
        assert bool(app.groot_key_file) == enabled
        assert app.groot_model == CONFIG['model']
    finally:
        shutil.rmtree(app.root)


def test_launch_uses_server_identity_and_rejects_other_checkpoint():
    app = playground.HostedRunner(public_origin='https://robot.example', session_api='https://session.example',
        camera_origin='https://session.example', robot_id='robohouse', hardware='yam',
        groot_key_file='/unused', groot_config=CONFIG,
        api_factory=lambda: MockSessionAPI(auto_activate=False))
    key = app.root / 'service-key'
    key.write_text('server-secret')
    app.groot_key_file = str(key)
    _, visitor = app.new_visitor()
    try:
        payload = {'provider':'groot','model':'groot-reviewed-step10000','prompt':'Place the cubes into the purple crate'}
        with pytest.raises(playground.RequestError, match='Unknown GR00T'):
            app.launch(visitor, payload)
        with patch.object(GrootAdapter, 'start_preparation'):
            result = app.launch(visitor, {**payload,'model':CONFIG['model']})
        assert result['ok']
        policy = visitor.controller._provider
        assert policy.model == CONFIG['model']
        assert policy._endpoint == CONFIG['endpoint']
        assert policy._artifact_sha256 == CONFIG['artifact_sha256']
        assert 'server-secret' not in str(visitor.controller.status())
        assert visitor.controller.status()['status'] == 'queued'
    finally:
        visitor.controller.stop()
        visitor.close()
        shutil.rmtree(app.root, ignore_errors=True)
