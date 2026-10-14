import pytest
from unittest.mock import Mock
from remote_yam.run_video_email import recipient
from remote_yam.session import HttpSessionAPI
from remote_yam.submission_log import LoggedSessionAPI, SubmissionLog


def test_video_request_requires_boolean_and_valid_email():
    assert recipient({}) == ''
    assert recipient({'email':'me@example.com'}) == ''
    assert recipient({'email':' me@example.com ', 'email_run_video':True}) == 'me@example.com'
    for payload in ({'email_run_video':True}, {'email_run_video':'true'}, {'email_run_video':1},
                    {'email_run_video':True,'email':'bad'}, {'email_run_video':True,'email':'a@b.c\nBcc: x@y.z'}):
        with pytest.raises(ValueError): recipient(payload)


def test_video_request_reaches_queue_and_resets_on_next_run(tmp_path):
    transport = HttpSessionAPI('https://api.example.test')
    transport.check_control_transport = lambda: None
    transport._request = Mock(return_value={'session_id':'s1','session_capability':'private'})
    logged = LoggedSessionAPI(transport, SubmissionLog(tmp_path/'submissions.db'))
    logged.setup({'email':'runner@example.com','email_run_video':True})
    logged.create_session('Move block')
    assert transport._request.call_args.args[2]['email_run_video'] is True
    assert transport._request.call_args.args[2]['email'] == 'runner@example.com'
    logged.setup({'email':'next@example.com','email_run_video':False})
    logged.create_session('Next task')
    assert 'email_run_video' not in transport._request.call_args.args[2]
    assert transport._request.call_args.args[2]['email'] == 'next@example.com'
