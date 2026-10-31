"""Run the pinned upstream workflow. Only provider selection is adapted here."""
import argparse
import json
import os
from pathlib import Path
from roboskills.core import llm
from roboskills.workflows.agentic_sim import run


def model_environment():
    # Pure simulation does not require the physical harness package. Keep only
    # login/runtime transport settings, excluding parent-agent thread overrides.
    allowed={'HOME','USER','LOGNAME','PATH','TMPDIR','TEMP','TMP','SYSTEMROOT','WINDIR',
             'CODEX_HOME','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','LANG','LC_ALL',
             'SSL_CERT_FILE','SSL_CERT_DIR','CODEX_CA_CERTIFICATE','HTTPS_PROXY','HTTP_PROXY',
             'ALL_PROXY','NO_PROXY','https_proxy','http_proxy','all_proxy','no_proxy'}
    return {key:value for key,value in os.environ.items() if key in allowed}


def execute(request, directory, python, model, hours=1.0, rounds=4):
    # Upstream's core supports Codex; agentic_sim currently selects only Claude
    # or DeepSeek. Bind the same tool-free conversation contract for GPT models.
    # Task construction, frozen-task checks, solver and seed validation stay upstream.
    if model.startswith('gpt-'):
        run.claude = lambda system, messages, **kwargs: llm.codex(
            'You generate Python for an external persistent REPL. The host executes it with write access. '
            'Your CLI sandbox does not restrict that external REPL. The host records timing.\n\n'+system,
            messages, model=model, effort='low', timeout=900, env=model_environment())
    run.BUILD = 'Runtime availability: MuJoCo and Blender are installed. Use these; PyBullet, Newton and NVIDIA RTX are unavailable on this worker.\n\n' + run.BUILD
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    options = dict(python=Path(os.path.abspath(python)), hours=hours, rounds=rounds, seeds=8, model=model)
    build = run.build(request['instruction'], directory/'build', **options)
    (directory/'build-result.json').write_text(json.dumps(build, indent=2))
    if not build.get('passed'):
        return {'passed': False, 'phase': 'build', 'build': build}
    (directory/'phase.json').write_text(json.dumps({'phase': 'solving'}))
    solve = run.solution(directory/'build', directory/'solve', **options)
    return {'passed': bool(solve.get('passed')), 'phase': 'solve', 'build': build, 'solve': solve}


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--out',required=True)
    p.add_argument('--python',required=True);p.add_argument('--model',default='gpt-6-astra');p.add_argument('--hours',type=float,default=1)
    a=p.parse_args()
    try:
        result=execute(json.loads(Path(a.request).read_text()),a.out,a.python,a.model,a.hours)
    except Exception as error:
        result={'passed':False,'error':type(error).__name__+': '+str(error)[:2000]}
    Path(a.out).mkdir(exist_ok=True,parents=True)
    (Path(a.out)/'result.json').write_text(json.dumps(result,indent=2))
    raise SystemExit(0 if result.get('passed') else 1)
