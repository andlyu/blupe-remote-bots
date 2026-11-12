// Authentic native tools/driver with synthetic feedback and a loopback-only station.
import path from 'node:path';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const root=process.env.KINEX_SOURCE;
const {Client}=await import(pathToFileURL(path.join(root,'node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js')));
const {StdioClientTransport}=await import(pathToFileURL(path.join(root,'node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js')));
const plan=JSON.parse(await readFile(process.argv[3],'utf8'));
const transport=new StdioClientTransport({command:'node',args:[path.join(import.meta.dirname,'mcp.mjs')],cwd:process.argv[2],env:{...process.env}});
const client=new Client({name:'kinex-native-offline-contract',version:'1.0.0'});
const fixture=async(body)=>{
 const response=await fetch(process.env.KINEX_FIXTURE+'/fixture',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+process.env.BLUPE_KINEX_TOKEN},body:JSON.stringify(body)});
 assert(response.ok);return response.json();
};
const results=[];
try{
 await client.connect(transport);
 const start=await client.callTool({name:'kinex_start',arguments:{}});assert(!start.isError,JSON.stringify(start));
 for(const item of plan){
  const before=await fixture({...item,observation:item.observation});
  let result;
  try{result=await client.callTool({name:item.tool||'device',arguments:item.arguments})}
  catch(error){result={isError:true,error:String(error)}}
  assert.equal(!!result.isError,!!item.reject,item.label+': '+JSON.stringify(result));
  if(item.reject_reason)assert.match(JSON.stringify(result),new RegExp(item.reject_reason),item.label+' planning rejection');
  if(item.image)assert(result.content.some(c=>c.type==='image'),item.label+' image attachment');
  const after=await fixture({inspect:true});
  assert.equal(after.dispatches-before.dispatches,item.writes||0,item.label+' dispatch count');
  results.push({label:item.label,rejected:!!result.isError,packets:after.dispatches-before.dispatches});
 }
 await client.callTool({name:'kinex_shutdown',arguments:{}});
 console.log(JSON.stringify({passed:true,physical_commands_sent:0,cases:results}));
}finally{await client.close()}
