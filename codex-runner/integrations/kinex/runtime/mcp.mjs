// Direct-schema façade over the official Kinex RuntimeSession/core.
// Lifecycle, permission rules, cancellation, images and drivers remain upstream-owned.
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const source=process.env.KINEX_SOURCE;
const upstream=async name=>import(pathToFileURL(path.join(source,name)));
const {RuntimeSession}=await upstream('packages/mcp/dist/session.js');
const {mcpInteraction}=await upstream('packages/mcp/dist/interaction.js');
const {modelResult}=await upstream('packages/mcp/dist/result.js');
const {coreContribution}=await upstream('node_modules/@kinex/core/dist/integration.js');
const {Server}=await upstream('node_modules/@modelcontextprotocol/sdk/dist/esm/server/index.js');
const {StdioServerTransport}=await upstream('node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js');
const {CallToolRequestSchema,ListToolsRequestSchema}=await upstream('node_modules/@modelcontextprotocol/sdk/dist/esm/types.js');
const allowed=new Set(['device','devices','device_stop','servo']);
const lifetime=new AbortController();
const server=new Server({name:'kinex',version:'1.0.0'},{capabilities:{tools:{}},instructions:'Kinex is already activated by the authorized robot host. Use the four native device tools with their supplied schemas. No start/discovery calls are needed. Hardware commands still require normal lease, measured readiness, local validation and gateway acceptance. Never retry uncertain motion.'});
const session=new RuntimeSession({directory:process.cwd(),permissionMode:'host',
 diagnostic:message=>process.stderr.write(message+'\n'),
 composition:{contributions(runtime){const core=coreContribution(runtime);return [{...core,commands:[],tools:{
  async list(){const catalog=await core.tools.list();return {...catalog,tools:catalog.tools.filter(t=>allowed.has(t.name))}},
  async call(name,input,invocation){if(!allowed.has(name))throw new Error('This public integration does not expose '+name);return core.tools.call(name,input,invocation)}
 }}]}}},mcpInteraction(server));
// The user explicitly requested this runtime through the hosted harness. The host
// starts it; explicit per-tool deny rules are still resolved by upstream Kinex.
await session.start(lifetime.signal,true);
server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:(await session.bundle.capabilities.tools.list()).tools}));
server.setRequestHandler(CallToolRequestSchema,async(request,extra)=>{
 try{
  const name=request.params.name,args=request.params.arguments||{};
  // Compatibility lifecycle is retained for offline verification, not advertised
  // to the model as a prerequisite or a redundant discovery round trip.
  if(name==='kinex_start'){await session.start(lifetime.signal,true);return {content:[{type:'text',text:JSON.stringify(session.status())}]}}
  if(name==='kinex_shutdown'){await session.shutdown();return {content:[{type:'text',text:JSON.stringify(session.status())}]}}
  if(name==='kinex_tools')return {content:[{type:'text',text:JSON.stringify(await session.bundle.capabilities.tools.list())}]};
  const tool=name==='kinex_call'?args.name:name,input=name==='kinex_call'?args.arguments:args;
  if(!allowed.has(tool))throw new Error('This public integration does not expose '+tool);
  return await session.run(extra.signal,tool==='device_stop',async(bundle,invocation)=>modelResult(await bundle.capabilities.tools.call(tool,input,{...invocation,callID:String(extra.requestId)})));
 }catch(error){return {isError:true,content:[{type:'text',text:error instanceof Error?error.name+': '+error.message:String(error)}]}}
});
let closing;
const dispose=()=>closing??=(async()=>{lifetime.abort();try{await session.shutdown()}finally{await server.close()}})();
server.onclose=()=>{void dispose().catch(error=>process.stderr.write(String(error)+'\n'))};
server.onerror=error=>process.stderr.write(String(error)+'\n');
await server.connect(new StdioServerTransport());
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>{void dispose().finally(()=>process.exit())});
