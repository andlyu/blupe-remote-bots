"""MolmoAct2 baseline / CAG-inspired variant through the existing BluPe queue."""
import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from local_playground import LocalPlayground, PUBLIC_SESSION_API
from playground import RequestError
from remote_yam.molmoact_policy import MolmoActAdapter, MODEL, VARIANT, comparison_options
from remote_yam.research_identity import research_runner

ROOT = Path(__file__).resolve().parent


class CAGPlayground(LocalPlayground):
    def __init__(self, *, runpod_key, endpoint, preview=False, runs_enabled=True, **kwargs):
        if kwargs.get('robot_id','yam-1') != 'yam-1' or tuple(kwargs.get('joint_counts',(6,6))) != (6,6) or kwargs.get('hardware','yam') != 'yam':
            raise ValueError('This pinned checkpoint supports only YAM1, with its top/left/right cameras and 6+6 joints')
        self.preview, self._runpod_key, self.endpoint = preview, runpod_key, endpoint
        self.runs_enabled = runs_enabled
        super().__init__(**kwargs, default_provider='molmoact_baseline', local_codex=False, local_claude=False)
        self.cookie_name += '-cag-' + str(urlsplit(kwargs['public_origin']).port or 443)
        for mode in ('baseline','guided'):
            self.extra_providers['molmoact_'+mode] = lambda model, directory, mode=mode: self.policy(model, mode)

    def policy(self, model, mode):
        if model not in ('', MODEL): raise RequestError(400,'Choose the pinned MolmoAct2 checkpoint')
        return MolmoActAdapter(self._runpod_key, camera_source=self.camera_source,
                              endpoint=self.endpoint, robot_id=self.robot_id, mode=mode)

    async def session_extension(self, cookies, visitor):
        metadata, headers=await super().session_extension(cookies,visitor)
        return {**metadata,'local_runner':True,'default_provider':'molmoact_baseline',
            'research_integration': dict(method='Completion Aware Guidance', variant=VARIANT,
                experimental=True, human_email_required=True, robot_id='yam-1', runs_enabled=self.runs_enabled),
            'configured_providers': {'molmoact_'+mode:dict(
                label='MolmoAct2 baseline' if mode=='baseline' else 'MolmoAct2 + CAG variant', model=MODEL,
                help=('Read-only preview. ' if self.preview else '')+'YAM1 · same pinned weights in both modes. Choose a task, select a mode, then press Run. The RunPod key stays on the server.')
                for mode in ('baseline','guided')}}, headers

    def page(self):
        return super().page().replace(b'<title>BluPe', b'<title>CAG + MolmoAct2').replace(b'<!-- application-head -->',
            b'<link rel="stylesheet" href="/static/cag-comparison.css"><script src="/static/cag-progress.js" defer></script><script src="/static/cag-comparison.js" defer></script>')

    async def public_extension(self, scope, receive, send, headers):
        if scope['method']=='GET' and scope['path'] in ('/static/cag-comparison.js','/static/cag-comparison.css','/static/cag-progress.js'):
            name=scope['path'].removeprefix('/static/')
            content_type='text/css' if name.endswith('.css') else 'application/javascript'
            await self.respond(send,200,(ROOT/'static'/name).read_bytes(),content_type)
            return True
        return await super().public_extension(scope,receive,send,headers)

    def decorate_history(self, value):
        # The media catalog is shared with BluPe, while this runner owns its
        # confirmed names and frozen method configuration. Keep both together.
        from remote_yam.past_runs import merge_run_result
        names=self.run_names.names()
        results=self.run_names.results()
        configurations={}
        if self.run_names.path.exists():
            with sqlite3.connect(self.run_names.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=2) as db:
                if db.execute("SELECT name FROM sqlite_master WHERE name='run_configuration'").fetchone():
                    configurations={eid:json.loads(config) for eid,config in db.execute('SELECT episode_id,configuration FROM run_configuration')}
        for row in value.get('runs',[]):
            eid=row.get('episode_id')
            if eid in names:row['runner_name']=names[eid]
            if eid in results:merge_run_result(row,results[eid])
            config=configurations.get(eid,{})
            if config.get('provider') in ('molmoact_baseline','molmoact_guided'):
                row['model']=config['model']
                row['model_version']=config['approach']
                row['approach']=config['approach']
                row['run_context']=config.get('run_context')
        return value

    async def http(self, scope, receive, send):
        if scope.get('method')!='GET' or scope.get('path')!='/api/past-runs':
            return await super().http(scope,receive,send)
        messages=[]
        async def capture(message):messages.append(message)
        await super().http(scope,receive,capture)
        if messages and messages[0].get('status')==200:
            data=json.loads(b''.join(m.get('body',b'') for m in messages[1:]))
            data=await asyncio.to_thread(self.decorate_history,data)
            return await self.json(send,200,data)
        for message in messages:await send(message)

    def launch(self, visitor, payload, **kwargs):
        if self.preview: raise RequestError(403,'Read-only comparison preview: robot runs are disabled')
        if not self.runs_enabled:
            raise RequestError(503,'GPU inference is paused. Live cameras and previous runs remain available.')
        name=payload.get('provider')
        if name not in ('molmoact_baseline','molmoact_guided'):
            raise RequestError(400,'Choose MolmoAct2 baseline or MolmoAct2 + CAG variant')
        try:
            mode,strength=comparison_options(name.removeprefix('molmoact_'),payload.get('guidance_strength',.15))
            runner=research_runner(payload)
        except (ValueError, AttributeError) as exc:
            raise RequestError(400,str(exc)) from None
        payload=dict(payload,runner_name=runner['name'])
        transform=kwargs.pop('provider_transform',None)
        def configure(provider):
            provider.mode,provider.strength=mode,strength
            provider.run_context=dict(method='Completion Aware Guidance', variant=VARIANT,
                approach='MolmoAct2 baseline' if mode=='baseline' else 'MolmoAct2 + CAG-inspired guidance',
                mode=mode,guidance_strength=strength,runner=runner)
            return transform(provider) if transform else provider
        result=super().launch(visitor,payload,provider_transform=configure,**kwargs)
        config=visitor.controller._provider.public_config()
        visitor.controller._session_api.note('research_context',config['run_context'],
            visitor.runner_session_id)
        visitor.controller._interactions.add('research_context',
            config['approach']+' · '+runner['name'], **config['run_context'])
        result['launch_message']='Starting RunPod GPU and loading MolmoAct2. The robot will join the queue when the model is ready.'
        return result

    def remember_runner(self, visitor):
        # GPU preparation creates the queue session asynchronously. Retain the
        # submitted identity once that session exists, including queue/replay labels.
        state=visitor.controller.status()
        session_id=state.get('session_id')
        if session_id and visitor.runner_task and visitor.runner_session_id != session_id:
            visitor.runner_session_id=session_id
            config=state.get('provider') or {}
            context=config.get('run_context')
            if context:
                visitor.controller._session_api.note('research_context',context,session_id)
                visitor.controller._interactions.add('research_context',
                    config.get('approach','MolmoAct2')+' · '+visitor.runner_name, **context)
                visitor.controller._interactions.add('runner','Run submitted by '+visitor.runner_name,runner_name=visitor.runner_name)
        super().remember_runner(visitor)


def create_app():
    """Hosted ASGI entrypoint. Never substitutes mock robot/model services."""
    import os
    origin=os.environ['CAG_PUBLIC_ORIGIN']
    key=Path(os.environ['CAG_RUNPOD_KEY_FILE']).read_text().strip()
    return CAGPlayground(public_origin=origin,session_api=os.environ.get('CAG_SESSION_API',PUBLIC_SESSION_API),
        camera_origin=os.environ.get('CAG_SESSION_API',PUBLIC_SESSION_API),
        development=False,hardware_control=True,share_conversation=False,
        runs_enabled=os.environ.get('CAG_RUNS_ENABLED')=='1',
        runpod_key=key,endpoint=os.environ['CAG_MODEL_ENDPOINT'],
        robot_id='yam-1',camera_names=('top','left','right'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',required=True,help='Separate RunPod HTTPS inference endpoint')
    parser.add_argument('--key-file',type=Path,default=Path.home()/'.config/runpod/api-key')
    parser.add_argument('--api',default=PUBLIC_SESSION_API)
    parser.add_argument('--port',type=int,default=8798)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    import uvicorn
    import webbrowser
    origin=f'http://127.0.0.1:{args.port}'
    app=CAGPlayground(public_origin=origin, session_api=None if args.preview else args.api,
        camera_origin='http://127.0.0.1:1' if args.preview else args.api,
        development=True,hardware_control=not args.preview,share_conversation=False,
        preview=args.preview,runpod_key='preview-only' if args.preview else args.key_file.expanduser().read_text().strip(),
        endpoint=args.endpoint,robot_id='yam-1',camera_names=('top','left','right'))
    print(f'MolmoAct2 comparison: {origin} · YAM1 · robot runs require Run',flush=True)
    if not args.no_browser: webbrowser.open(origin)
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__': main()
