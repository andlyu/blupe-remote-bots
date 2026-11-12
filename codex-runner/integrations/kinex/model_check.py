"""Non-actuating Astra/Kinex check using offline device profiles."""
import json,os
from pathlib import Path
import subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2];PROJECT=ROOT.parent
upstream=PROJECT/'output/kinex-upstream'
workspace=Path('/tmp/kinex-last-offline-workspace').read_text()
env=dict(os.environ,KINEX_SOURCE=str(upstream));env.pop('OPENAI_API_KEY',None)
settings={'forced_login_method':'chatgpt','model_provider':'openai','model_reasoning_effort':'low','approval_policy':'on-request',
 'web_search':'disabled','features.shell_tool':False,'features.apps':False,'features.multi_agent':False,'features.hooks':False,
 'mcp_servers.kinex.command':'node','mcp_servers.kinex.args':[str(ROOT/'integrations/kinex/runtime/mcp.mjs')],
 'mcp_servers.kinex.env_vars':['KINEX_SOURCE','BLUPE_KINEX_PYTHON','BLUPE_KINEX_BRIDGE','BLUPE_KINEX_TOKEN'],
            'mcp_servers.kinex.required':True,'mcp_servers.kinex.default_tools_approval_mode':'approve'}
command=[str(upstream/'node_modules/.bin/codex'),'exec','--ignore-user-config','--skip-git-repo-check','--json','--sandbox','read-only','--model','gpt-6-astra','-C',workspace]
for key,value in settings.items():command+=['-c',key+'='+json.dumps(value)]
command+=['-']
output=PROJECT/'output/kinex-model-check'/('attempt-'+str(int(time.time())));output.mkdir(parents=True,exist_ok=True)
start=time.time()
with (output/'events.jsonl').open('w') as stdout,(output/'stderr.log').open('w') as stderr:
 r=subprocess.run(command,input='This is a non-actuating integration check initiated by andrew. These are offline profiles, not a real robot connection. Call kinex_start, discover the device schema, and read only the world clock with kinex_call. Do not call any physical arm, gripper, camera, or motion tool. Then call kinex_shutdown and report the clock result.',text=True,stdout=stdout,stderr=stderr,env=env,timeout=120)
events=[]
for line in (output/'events.jsonl').read_text().splitlines():
 try:events.append(json.loads(line))
 except ValueError:pass
receipt=dict(exit_code=r.returncode,elapsed_s=time.time()-start,runner_name='andrew',execution_mode='automated_verification',approach='Kinex',requested_model='gpt-6-astra',resolved_model=None,physical_connection=False,physical_commands_sent=0,tools=[e.get('item',{}).get('tool') for e in events if e.get('item',{}).get('type')=='mcp_tool_call'],errors=[e for e in events if e.get('type') in ('error','turn.failed')],final=[e['item']['text'] for e in events if e.get('item',{}).get('type')=='agent_message'])
(output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
