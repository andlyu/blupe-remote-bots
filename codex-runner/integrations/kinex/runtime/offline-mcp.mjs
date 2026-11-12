// Real Kinex MCP/core lifecycle test, without a model or physical robot.
import path from 'node:path';import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const source=process.env.KINEX_SOURCE;
const {Client}=await import(pathToFileURL(path.join(source,'node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js')));
const {StdioClientTransport}=await import(pathToFileURL(path.join(source,'node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js')));
const transport=new StdioClientTransport({command:'node',args:[path.resolve('codex-runner/integrations/kinex/runtime/mcp.mjs')],cwd:process.argv[2],env:{...process.env}});
const client=new Client({name:'kinex-blupe-offline',version:'1.0.0'});
try{
 await client.connect(transport);
 const start=await client.callTool({name:'kinex_start',arguments:{}});assert(!start.isError,JSON.stringify(start));
 const list=await client.callTool({name:'kinex_tools',arguments:{}});assert(!list.isError,JSON.stringify(list));
 const value=JSON.parse(list.content.find(c=>c.type==='text').text);const names=value.tools.map(t=>t.name);
 assert(names.includes('device'));assert(names.includes('servo'));assert(!names.includes('exec'));
 const clock=await client.callTool({name:'kinex_call',arguments:{name:'device',arguments:{deviceID:'world',action:'read'}}});assert(!clock.isError,JSON.stringify(clock));
 const denied=await client.callTool({name:'kinex_call',arguments:{name:'exec',arguments:{source:'raise Exception()'}}});assert(denied.isError);
 await client.callTool({name:'kinex_shutdown',arguments:{}});
 console.log(JSON.stringify({passed:true,catalog:names,clock:true,unrestricted_exec_rejected:true}));
}finally{await client.close()}
