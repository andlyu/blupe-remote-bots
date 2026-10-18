import json
from pathlib import Path
import pytest
from remote_yam.resets.cube_runner import run_cube_reset


def config():
    return dict(cube_args=['--feedback-close-gap-mm','20','--home-after-replay','--staging-feedback'],
        transport=dict(ssh='fixture@robot',identity='/fixture/key'),resources={},io_routes={},replay={},recipe={})


def test_fresh_cube_only_runs_bind_receipts_and_preserve_grip_profile(tmp_path):
    calls=[]
    def cli(args):
        calls.append(args);child=Path(args[args.index('--output')+1]);child.mkdir()
        (child/'result.json').write_text(json.dumps(dict(state='complete',goals_reached=True)))
        return 0
    for request in ('first','second'):
        result=run_cube_reset(config(),tmp_path/request,request_id=request,cube_main=cli)
        assert result==dict(state='complete',goals_reached=True,request_id=request,replay_requested=False,cube_cli_exit_code=0)
        assert '--home-after-replay' not in calls[-1] and '--after-replay' not in calls[-1]
        assert calls[-1][calls[-1].index('--feedback-close-gap-mm')+1]=='20'
    with pytest.raises(FileExistsError):run_cube_reset(config(),tmp_path/'first',cube_main=cli)
    assert len(calls)==2


@pytest.mark.parametrize('failure',[KeyboardInterrupt(),RuntimeError('fixture failure')])
def test_cancellation_and_error_leave_request_bound_receipts(tmp_path,failure):
    def cli(args):raise failure
    result=run_cube_reset(config(),tmp_path/'run',request_id='this-run',cube_main=cli)
    assert result['state']==('cancelled' if isinstance(failure,KeyboardInterrupt) else 'failed')
    assert result['request_id']=='this-run' and not result['goals_reached']
