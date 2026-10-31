import { env } from 'cloudflare:workers';
import { getChatGPTUser } from '../../chatgpt-auth';
import { skills } from '../../../lib/skills';
export const dynamic='force-dynamic';
type Bindings={DB:D1Database;BUCKET:R2Bucket;WORKER_TOKEN?:string;SIMULATION_WORKER_TOKEN?:string;RUNNER_OWNER_EMAIL?:string};
type Row={id:string;owner:string;skill:string;instruction:string;runner_name:string;runner_email:string;status:string;stage:string;created_at:number;updated_at:number;cancel_requested:number;worker:string|null;result:string|null;assets:string};
const active=['queued','building','solving','uploading'];
function publicRun(r:Row){return {id:r.id,skill:r.skill,instruction:r.instruction,runnerName:r.runner_name,status:r.status,stage:r.stage,createdAt:r.created_at,updatedAt:r.updated_at,cancelRequested:!!r.cancel_requested,result:r.result?JSON.parse(r.result):null,assets:JSON.parse(r.assets)};}
const reply=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
const fail=(error:string,status=400)=>reply({error},status);
function sameOrigin(req:Request){return req.headers.get('origin')===new URL(req.url).origin;}
async function route(req:Request,{params}:{params:Promise<{path:string[]}>}) {
 const path=(await params).path,db=(env as unknown as Bindings).DB,bucket=(env as unknown as Bindings).BUCKET;
 if(!db)return fail('Simulation storage is unavailable. Refresh to reconnect.',503);
 const now=Date.now();
 if(path[0]==='worker'){
  const b=env as unknown as Bindings,token=b.SIMULATION_WORKER_TOKEN||b.WORKER_TOKEN;
  if(!token||req.headers.get('authorization')!=='Bearer '+token)return fail('Worker authentication required.',401);
  if(req.method!=='POST')return fail('Use POST.',405);
  if(path[1]==='upload'){
   const url=new URL(req.url),id=url.searchParams.get('id')||'',name=url.searchParams.get('name')||'',worker=req.headers.get('x-worker-id');
   if(!/^[a-f0-9]{32}$/.test(id)||! /^(?:build|solve)\.(?:mp4|json|py)$|^(?:task|solution|notes)\.(?:py|md)$/.test(name))return fail('Invalid output name.');
   const row=await db.prepare('SELECT * FROM runs WHERE id=? AND worker=?').bind(id,worker).first<Row>();
   if(!row||!active.includes(row.status))return fail('Run is not owned by this worker.',403);
   const data=await req.arrayBuffer();if(data.byteLength>32*1024*1024)return fail('Output exceeds 32 MB.',413);
   await bucket.put(id+'/'+name,data,{httpMetadata:{contentType:name.endsWith('.mp4')?'video/mp4':name.endsWith('.json')?'application/json':'text/plain; charset=utf-8'}});
   const assets:string[]=JSON.parse(row.assets);if(!assets.includes(name))assets.push(name);
   await db.prepare('UPDATE runs SET assets=?,updated_at=? WHERE id=? AND worker=?').bind(JSON.stringify(assets),now,id,worker).run();return reply({ok:true});
  }
  let data;try{data=await req.json() as Record<string,unknown>;}catch{return fail('Expected JSON.');}
  const worker=typeof data.worker==='string'&&/^[a-f0-9]{32}$/.test(data.worker)?data.worker:null;if(!worker)return fail('Invalid worker identity.');
  if(path[1]==='heartbeat'){
   await db.prepare('INSERT INTO workers(id,heartbeat,detail) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,detail=excluded.detail').bind(worker,now,String(data.detail||'Ready to build and solve a new scene.').slice(0,300)).run();
   if(typeof data.run==='string')await db.prepare('UPDATE runs SET updated_at=? WHERE id=? AND worker=? AND status IN (?,?,?)').bind(now,data.run,worker,'building','solving','uploading').run();
   const row=typeof data.run==='string'?await db.prepare('SELECT cancel_requested FROM runs WHERE id=? AND worker=?').bind(data.run,worker).first<{cancel_requested:number}>():null;
   return reply({ok:true,cancel:!!row?.cancel_requested});
  }
  if(path[1]==='claim'){
   const row=await db.prepare("UPDATE runs SET worker=?,status='building',stage='Building the task. The agent is creating the scene and native success checks.',updated_at=? WHERE id=(SELECT id FROM runs WHERE status='queued' AND cancel_requested=0 ORDER BY created_at LIMIT 1) AND status='queued' RETURNING *").bind(worker,now).first<Row>();return reply({run:row?{...publicRun(row),runnerEmail:row.runner_email}:null});
  }
  if(path[1]==='update'){
   if(typeof data.id!=='string'||!['building','solving','uploading','passed','failed','cancelled'].includes(String(data.status)))return fail('Invalid run update.');
   const current=await db.prepare('SELECT * FROM runs WHERE id=? AND worker=?').bind(data.id,worker).first<Row>();if(!current||!active.includes(current.status))return fail('Run is no longer active.',409);
   const result=data.result?JSON.stringify(data.result):null;if(result&&result.length>200000)return fail('Result too large.',413);
   await db.prepare('UPDATE runs SET status=?,stage=?,result=COALESCE(?,result),updated_at=? WHERE id=? AND worker=?').bind(data.status,String(data.stage||'').slice(0,1000),result,now,data.id,worker).run();return reply({ok:true});
  }
  return fail('Unknown worker action.',404);
 }
 if(path[0]==='config'&&req.method==='GET'){
  const worker=await db.prepare('SELECT * FROM workers ORDER BY heartbeat DESC LIMIT 1').first<{heartbeat:number;detail:string}>();
  const online=!!worker&&now-worker.heartbeat<20000;return reply({online,detail:online?worker.detail:'Connect the project’s simulation worker to run a new task. The upstream demonstrations are available now.'});
 }
 // Public demo history and artifacts contain no owner IDs or email addresses.
 if(path[0]==='runs'&&req.method==='GET'){
  if(path.length===1){const rows=await db.prepare('SELECT * FROM runs ORDER BY created_at DESC LIMIT 50').all<Row>();return reply({runs:rows.results.map(publicRun)});}
  const row=await db.prepare('SELECT * FROM runs WHERE id=?').bind(path[1]).first<Row>();if(!row)return fail('Run not found.',404);
  if(path[2]==='assets'&&path.length===4){
   if(!JSON.parse(row.assets).includes(path[3]))return fail('Output not found.',404);
   const obj=await bucket.get(row.id+'/'+path[3],{range:req.headers});if(!obj)return fail('Output not found.',404);
   const headers=new Headers({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Accept-Ranges':'bytes'});obj.writeHttpMetadata(headers);
   let status=200;if(obj.range&&'offset' in obj.range&&obj.range.offset!==undefined){const length=obj.range.length||obj.size;headers.set('Content-Range',`bytes ${obj.range.offset}-${obj.range.offset+length-1}/${obj.size}`);status=206;}
   return new Response(obj.body,{status,headers});
  }
  if(path.length===2)return reply({run:publicRun(row)});
 }
 const user=await getChatGPTUser();const ownerEmail=(env as unknown as Bindings).RUNNER_OWNER_EMAIL;
 if(!user||!ownerEmail||user.email.toLowerCase()!==ownerEmail.toLowerCase())return fail('The shared simulation worker is available to its operator. The YAM demonstrations and local workflow are public.',403);
 if(req.method==='POST'&&!sameOrigin(req))return fail('Reload the website before submitting a task.',403);
 if(path[0]==='runs'&&path.length===1){
  if(req.method==='GET'){
   // Mark abandoned work explicitly. It is never automatically retried.
   await db.prepare("UPDATE runs SET status='failed',stage='The simulation worker disconnected. Start a new run when it reconnects.',updated_at=? WHERE owner=? AND status IN ('building','solving','uploading') AND updated_at<?").bind(now,user.userId,now-120000).run();
   const rows=await db.prepare('SELECT * FROM runs WHERE owner=? ORDER BY created_at DESC LIMIT 50').bind(user.userId).all<Row>();return reply({runs:rows.results.map(publicRun)});
  }
  if(req.method==='POST'){
   if(Number(req.headers.get('content-length')||0)>16000)return fail('Task is too large.',413);
   let body;try{body=await req.json() as Record<string,unknown>;}catch{return fail('Expected JSON.');}
   if(!skills.some(s=>s.id===body.skill)||typeof body.instruction!=='string'||body.instruction.trim().length<30||body.instruction.length>3000)return fail('Describe a bimanual task in 30–3,000 characters.');
   if(typeof body.runnerName!=='string'||!body.runnerName.trim()||body.runnerName.length>80||typeof body.runnerEmail!=='string'||! /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(body.runnerEmail)||body.runnerEmail.length>200)return fail('Enter your name and a valid email.');
   const worker=await db.prepare('SELECT heartbeat FROM workers ORDER BY heartbeat DESC LIMIT 1').first<{heartbeat:number}>();if(!worker||now-worker.heartbeat>20000)return fail('The simulation runner is offline. Connect it, then try again. Your instruction has been kept.',503);
   const existing=await db.prepare("SELECT id FROM runs WHERE owner=? AND status IN ('queued','building','solving','uploading') LIMIT 1").bind(user.userId).first();if(existing)return fail('You already have an active simulation. Stop it or wait for its result.',409);
   const id=crypto.randomUUID().replaceAll('-','');
   await db.prepare('INSERT INTO runs(id,owner,skill,instruction,runner_name,runner_email,status,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)').bind(id,user.userId,body.skill,body.instruction.trim(),body.runnerName.trim(),body.runnerEmail.trim(),'queued','Waiting for the simulation worker to accept this task.',now,now).run();
   return reply({run:publicRun((await db.prepare('SELECT * FROM runs WHERE id=?').bind(id).first<Row>())!)},201);
  }
 }
 if(path[0]==='runs'&&/^[a-f0-9]{32}$/.test(path[1]||'')){
  const row=await db.prepare('SELECT * FROM runs WHERE id=? AND owner=?').bind(path[1],user.userId).first<Row>();if(!row)return fail('Run not found.',404);
  if(path[2]==='stop'&&req.method==='POST'){
   if(row.status==='queued')await db.prepare("UPDATE runs SET cancel_requested=1,status='cancelled',stage='Cancelled before execution.',updated_at=? WHERE id=? AND status='queued'").bind(now,row.id).run();
   else if(active.includes(row.status))await db.prepare('UPDATE runs SET cancel_requested=1 WHERE id=?').bind(row.id).run();return reply({ok:true});
  }
  if(path[2]==='assets'&&path.length===4&&req.method==='GET'){
   if(!JSON.parse(row.assets).includes(path[3]))return fail('Output not found.',404);
   const obj=await bucket.get(row.id+'/'+path[3],{range:req.headers});if(!obj)return fail('Output not found.',404);
   const headers=new Headers({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Accept-Ranges':'bytes'});obj.writeHttpMetadata(headers);
   let status=200;if(obj.range&&'offset' in obj.range&&obj.range.offset!==undefined){const length=obj.range.length||obj.size;headers.set('Content-Range',`bytes ${obj.range.offset}-${obj.range.offset+length-1}/${obj.size}`);status=206;}
   return new Response(obj.body,{status,headers});
  }
  if(path.length===2&&req.method==='GET')return reply({run:publicRun(row)});
 }
 return fail('Route not found.',404);
}
async function safe(req:Request,ctx:{params:Promise<{path:string[]}>}){try{return await route(req,ctx);}catch(e){if(e instanceof Error && /runs.owner|runs_one_active_owner/.test(e.message))return fail('You already have an active simulation. Stop it or wait for its result.',409);console.error('Workspace request failed',e instanceof Error?e.message:'unknown');return fail('The workspace could not finish this request. Your task has been kept; refresh to reconnect.',500);}}
export const GET=safe;export const POST=safe;
