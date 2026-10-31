const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const {webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..');
function load(file,bindings){
 const module={exports:{}};
 const code=ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
 vm.runInNewContext(code,{module,exports:module.exports,require:name=>{if(!(name in bindings))throw Error('Unexpected import '+name);return bindings[name]},Request,Response,Headers,URL,crypto:webcrypto,Uint8Array,Date,console,AbortSignal},{filename:file});
 return module.exports;
}
function setup(){
 const rows=[];
 const db={prepare(sql){let args;const statement={bind(...values){args=values;return statement},async first(){
  if(sql==='SELECT heartbeat FROM physical_workers ORDER BY heartbeat DESC LIMIT 1')return {heartbeat:Date.now()};
  if(sql.startsWith('SELECT id FROM physical_runs WHERE status IN'))return rows.find(r=>['queued','preparing','running','recording'].includes(r.status))||null;
  if(sql==='SELECT * FROM physical_runs WHERE id=?')return rows.find(r=>r.id===args[0])||null;
  if(sql==='SELECT * FROM physical_runs WHERE id=? AND owner=?')return rows.find(r=>r.id===args[0]&&r.owner===args[1])||null;
  throw Error('Unexpected first SQL '+sql);
 },async all(){assert.equal(sql,'SELECT * FROM physical_runs ORDER BY created_at DESC LIMIT 50');return {results:rows}},async run(){
  if(sql.startsWith('INSERT INTO physical_runs(')){
   const [id,owner,instruction,runner_name,runner_email,status,stage,created_at,updated_at]=args;
   rows.push({id,owner,instruction,runner_name,runner_email,status,stage,created_at,updated_at,cancel_requested:0,result:null,assets:'[]'});return;
  }
  if(sql.startsWith("UPDATE physical_runs SET status='cancelled'")){const row=rows.find(r=>r.id===args[1]);row.status='cancelled';row.cancel_requested=1;return;}
  throw Error('Unexpected run SQL '+sql);
 }};return statement}};
 const visitor=load('app/physical-visitor.ts',{});
 const route=load('app/api/physical/[...path]/route.ts',{'cloudflare:workers':{env:{DB:db,BUCKET:{}}},'../../../chatgpt-auth':{getChatGPTUser:async()=>null},'../../../physical-visitor':visitor});
 const origin='https://example.test';
 async function request(parts,method='GET',body,cookie,requestOrigin=origin){
  const headers={};if(method==='POST')headers.Origin=requestOrigin;
  if(cookie)headers.Cookie=cookie;
  if(body)headers['Content-Type']='application/json';
  const req=new Request(origin+'/api/physical/'+parts.join('/'),{method,headers,...(body?{body:JSON.stringify(body)}:{})});
  return route[method](req,{params:Promise.resolve({path:parts})});
 }
 const task={instruction:'Raise both fingertips by20mm then return after a one second hold.',runnerName:'Test Runner',runnerEmail:'runner@example.test'};
 return {rows,request,task};
}
test('anonymous visitor joins without sign-in and gets private Stop capability',async()=>{
 const {rows,request,task}=setup(),response=await request(['runs'],'POST',task);
 assert.equal(response.status,201);
 const cookie=response.headers.get('set-cookie');
 for(const flag of ['HttpOnly','Secure','SameSite=Strict','Path=/'])assert.ok(cookie.includes(flag));
 const {run}=await response.json();assert.equal(run.canStop,true);assert.equal(run.runnerName,task.runnerName);
 assert.equal(run.owner,undefined);assert.equal(run.runnerEmail,undefined);assert.equal(rows[0].runner_email,task.runnerEmail);
});
test('same browser can Stop its own queued run; another browser cannot',async()=>{
 const {rows,request,task}=setup(),created=await request(['runs'],'POST',task),{run}=await created.json();
 const cookie=created.headers.get('set-cookie').split(';')[0];
 assert.equal((await request(['runs',run.id,'stop'],'POST',{})).status,403);
 assert.equal((await request(['runs',run.id,'stop'],'POST',{},'__Host-blupe-physical='+'a'.repeat(64))).status,404);
 assert.equal(rows[0].status,'queued');
 assert.equal((await request(['runs',run.id,'stop'],'POST',{},cookie)).status,200);assert.equal(rows[0].status,'cancelled');
});
test('public history has no contact or ownership capability and only own browser can Stop',async()=>{
 const {request,task}=setup(),created=await request(['runs'],'POST',task);const cookie=created.headers.get('set-cookie').split(';')[0];
 const publicRun=(await (await request(['runs'])).json()).runs[0],ownRun=(await (await request(['runs'],'GET',null,cookie)).json()).runs[0];
 assert.equal(publicRun.canStop,false);assert.equal(ownRun.canStop,true);
 for(const key of ['owner','runner_email','runnerEmail'])assert.equal(publicRun[key],undefined);
});
test('cross-origin launch is rejected before a job is inserted',async()=>{
 const {rows,request,task}=setup();assert.equal((await request(['runs'],'POST',task,null,'https://other.test')).status,403);assert.equal(rows.length,0);
});
test('confirmed name/email remain mandatory without sign-in',async()=>{
 const {rows,request,task}=setup();assert.equal((await request(['runs'],'POST',{...task,runnerName:''})).status,400);assert.equal((await request(['runs'],'POST',{...task,runnerEmail:''})).status,400);assert.equal(rows.length,0);
});
test('an active physical job prevents a second shared run',async()=>{
 const {rows,request,task}=setup();assert.equal((await request(['runs'],'POST',task)).status,201);assert.equal((await request(['runs'],'POST',task)).status,409);assert.equal(rows.length,1);
});
test('anonymous visitor cannot use application worker endpoints',async()=>{
 const {request}=setup();assert.equal((await request(['worker','claim'],'POST',{})).status,401);
});
