import {env} from 'cloudflare:workers';
import {getChatGPTUser} from '../../../chatgpt-auth';
export const dynamic='force-dynamic';
const ORIGIN='https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com';
type B={DB:D1Database;BUCKET:R2Bucket;WORKER_TOKEN?:string;RUNNER_OWNER_EMAIL?:string};
type Row={id:string;owner:string;instruction:string;runner_name:string;runner_email:string;status:string;stage:string;created_at:number;updated_at:number;worker:string|null;cancel_requested:number;result:string|null;assets:string};
const json=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const fail=(error:string,status=400)=>json({error},status);
const visible=(r:Row)=>({id:r.id,instruction:r.instruction,runnerName:r.runner_name,status:r.status,stage:r.stage,createdAt:r.created_at,updatedAt:r.updated_at,cancelRequested:!!r.cancel_requested,result:r.result?JSON.parse(r.result):null,assets:JSON.parse(r.assets),approach:'RoboSkills',robot:'yam-1',execution:'physical'});
const active=['queued','preparing','running','recording'];
async function route(req:Request,{params}:{params:Promise<{path:string[]}>}){
 const path=(await params).path,b=env as unknown as B,db=b.DB,now=Date.now();
 if(path[0]==='station'&&req.method==='GET'){
  const [q,o]=await Promise.all(['queue','observation'].map(p=>fetch(ORIGIN+'/v1/robots/yam-1/'+p,{signal:AbortSignal.timeout(5000)}).then(async r=>{if(!r.ok)throw Error('BluPe station unavailable');return r.json() as Promise<Record<string,unknown>>;})));
  const w=await db.prepare('SELECT * FROM physical_workers ORDER BY heartbeat DESC LIMIT 1').first<{heartbeat:number;detail:string}>();
  return json({queue:q,observation:o,runnerOnline:!!w&&now-w.heartbeat<15000,runnerDetail:w&&now-w.heartbeat<15000?w.detail:'The RoboSkills BluPe runner is disconnected.'});
 }
 if(path[0]==='camera'&&req.method==='GET'&&['left','top','right'].includes(path[1])){
  const r=await fetch(ORIGIN+'/v1/robots/yam-1/cameras/'+path[1]+'.jpg',{signal:AbortSignal.timeout(5000)});
  return new Response(r.body,{status:r.status,headers:{'Content-Type':'image/jpeg','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
 }
 if(path[0]==='worker'){
  if(!b.WORKER_TOKEN||req.headers.get('authorization')!=='Bearer '+b.WORKER_TOKEN)return fail('Worker authentication required',401);
  if(req.method!=='POST')return fail('Use POST',405);
  const worker=req.headers.get('x-worker-id')||'';if(!/^[a-f0-9]{32}$/.test(worker))return fail('Invalid worker');
  if(path[1]==='upload'){
   const url=new URL(req.url),id=url.searchParams.get('id')||'',name=url.searchParams.get('name')||'';
   if(!/^[a-f0-9]{32}$/.test(id)||!['physical.mp4','result.json'].includes(name))return fail('Invalid artifact');
   const row=await db.prepare('SELECT * FROM physical_runs WHERE id=? AND worker=?').bind(id,worker).first<Row>();
   if(!row)return fail('Run is not owned by this worker',403);
   const data=await req.arrayBuffer();if(data.byteLength>32*1024*1024)return fail('Recording exceeds32MB',413);
   await b.BUCKET.put('physical/'+id+'/'+name,data,{httpMetadata:{contentType:name.endsWith('.mp4')?'video/mp4':'application/json'}});
   const assets:string[]=JSON.parse(row.assets);if(!assets.includes(name))assets.push(name);
   await db.prepare('UPDATE physical_runs SET assets=?,updated_at=? WHERE id=? AND worker=?').bind(JSON.stringify(assets),now,id,worker).run();return json({ok:true});
  }
  const data=await req.json() as {id?:string;status?:string;stage?:string;result?:unknown;detail?:string};
  if(path[1]==='heartbeat'){
   await db.prepare('INSERT INTO physical_workers(id,heartbeat,detail) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,detail=excluded.detail').bind(worker,now,String(data.detail||'BluPe harness connected').slice(0,500)).run();
   if(data.id)await db.prepare('UPDATE physical_runs SET updated_at=? WHERE id=? AND worker=?').bind(now,data.id,worker).run();
   const r=data.id?await db.prepare('SELECT cancel_requested FROM physical_runs WHERE id=? AND worker=?').bind(data.id,worker).first<{cancel_requested:number}>():null;return json({cancel:!!r?.cancel_requested});
  }
  if(path[1]==='claim'){
   const row=await db.prepare("UPDATE physical_runs SET worker=?,status='preparing',stage='BluPe is joining the YAM queue and checking readiness.',updated_at=? WHERE id=(SELECT id FROM physical_runs WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1) AND status='queued' RETURNING *").bind(worker,now).first<Row>();return json({run:row?{...visible(row),runnerEmail:row.runner_email}:null});
  }
  if(path[1]==='update'){
   if(!['preparing','running','recording','finished','failed','cancelled'].includes(data.status||''))return fail('Invalid state');
   const result=data.result?JSON.stringify(data.result):null;if(result&&result.length>200000)return fail('Result too large',413);
   await db.prepare("UPDATE physical_runs SET status=?,stage=?,result=COALESCE(?,result),updated_at=? WHERE id=? AND worker=? AND status IN ('preparing','running','recording')").bind(data.status,String(data.stage||'').slice(0,1000),result,now,data.id,worker).run();return json({ok:true});
  }
  return fail('Unknown worker action',404);
 }
 if(path[0]==='runs'&&req.method==='GET'){
  if(path.length===1){const rows=await db.prepare('SELECT * FROM physical_runs ORDER BY created_at DESC LIMIT 50').all<Row>();return json({runs:rows.results.map(visible)});}
  const row=await db.prepare('SELECT * FROM physical_runs WHERE id=?').bind(path[1]).first<Row>();if(!row)return fail('Run not found',404);
  if(path[2]==='assets'&&path.length===4){
   if(!JSON.parse(row.assets).includes(path[3]))return fail('Recording is not ready yet',404);
   const obj=await b.BUCKET.get('physical/'+row.id+'/'+path[3],{range:req.headers});if(!obj)return fail('Artifact not found',404);
   const headers=new Headers({'Cache-Control':'no-store','Accept-Ranges':'bytes','X-Content-Type-Options':'nosniff'});obj.writeHttpMetadata(headers);
   let status=200;if(obj.range&&'offset' in obj.range&&obj.range.offset!==undefined){const len=obj.range.length||obj.size;headers.set('Content-Range',`bytes ${obj.range.offset}-${obj.range.offset+len-1}/${obj.size}`);status=206;}
   return new Response(obj.body,{status,headers});
  }
  return json({run:visible(row)});
 }
 const user=await getChatGPTUser();if(!user||user.email.toLowerCase()!==b.RUNNER_OWNER_EMAIL?.toLowerCase())return fail('Physical runs use the connected operator’s BluPe runner. Live views and replays are public.',403);
 if(req.method!=='POST'||req.headers.get('origin')!==new URL(req.url).origin)return fail('Reload before submitting',403);
 if(path[0]==='runs'&&path.length===1){
  const data=await req.json() as {instruction?:string;runnerName?:string;runnerEmail?:string};
  if(typeof data.instruction!=='string'||data.instruction.trim().length<30||data.instruction.length>3000||typeof data.runnerName!=='string'||!data.runnerName.trim()||data.runnerName.length>32||typeof data.runnerEmail!=='string'||! /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.runnerEmail)||data.runnerEmail.length>200)return fail('Enter a task, your name (up to32 characters) and email.');
  const w=await db.prepare('SELECT heartbeat FROM physical_workers ORDER BY heartbeat DESC LIMIT 1').first<{heartbeat:number}>();if(!w||now-w.heartbeat>15000)return fail('The RoboSkills BluPe runner is disconnected. Your task is kept.',503);
  const busy=await db.prepare("SELECT id FROM physical_runs WHERE status IN ('queued','preparing','running','recording') LIMIT 1").first();if(busy)return fail('A physical run is active. Wait for its result or use Stop.',409);
  const id=crypto.randomUUID().replaceAll('-','');await db.prepare('INSERT INTO physical_runs(id,owner,instruction,runner_name,runner_email,status,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)').bind(id,user.userId,data.instruction.trim(),data.runnerName.trim(),data.runnerEmail.trim(),'queued','Waiting for the BluPe harness to accept this run.',now,now).run();return json({run:visible((await db.prepare('SELECT * FROM physical_runs WHERE id=?').bind(id).first<Row>())!)},201);
 }
 if(path[0]==='runs'&&path[2]==='stop'){
  const row=await db.prepare('SELECT * FROM physical_runs WHERE id=? AND owner=?').bind(path[1],user.userId).first<Row>();if(!row)return fail('Run not found',404);
  if(row.status==='queued')await db.prepare("UPDATE physical_runs SET status='cancelled',cancel_requested=1,stage='Cancelled before joining BluPe.',updated_at=? WHERE id=? AND status='queued'").bind(now,row.id).run();
  else await db.prepare('UPDATE physical_runs SET cancel_requested=1 WHERE id=?').bind(row.id).run();return json({ok:true});
 }
 return fail('Route not found',404);
}
async function safe(req:Request,ctx:{params:Promise<{path:string[]}>}){try{return await route(req,ctx);}catch(e){console.error('Physical workspace request failed',e instanceof Error?e.message:'unknown');return fail('BluPe could not finish this request. Refresh status before starting another run.',503);}}
export const GET=safe;export const POST=safe;
