// Exercise the actual gateway with Cloudflare's documented redirect contract.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=(await readFile(new URL('../site/worker.js',import.meta.url),'utf8')).replace("import {PAGE} from './page.js';","const PAGE='Gemini';");
const {default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const originalFetch=globalThis.fetch;let upstreamStatus=200,requests=[];
globalThis.fetch=async(url,init)=>{
 if(init.redirect==='error')throw new TypeError('Cloudflare Workers does not implement redirect:error');
 requests.push({url,init});
 return new Response(new Uint8Array([255,216,255,217]),{status:upstreamStatus,headers:{'Content-Type':'image/jpeg'}});
};
try{
 const request=()=>new Request('https://gemini.example/api/cameras/top');
 let response=await worker.fetch(request(),{});
 assert.equal(response.status,200,'Camera must work under the actual Cloudflare redirect contract');
 assert.equal(response.headers.get('Content-Type'),'image/jpeg');
 assert.equal(requests[0].init.redirect,'manual');
 assert.equal(requests[0].url,'https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com/v1/robots/yam-1/cameras/top.jpg');
 upstreamStatus=302;response=await worker.fetch(request(),{});
 assert.equal(response.status,503,'Unexpected upstream redirect must not be followed');
 assert.equal(requests.length,2);
 response=await worker.fetch(new Request('https://gemini.example/api/runs',{method:'POST',headers:{Origin:'https://other.example'}}),{});
 assert.equal(response.status,403);
 response=await worker.fetch(new Request('https://gemini.example/api/identity'),{});
 assert.deepEqual(await response.json(),{name:'',email:''});
 console.log('Gateway camera, redirect, origin and anonymous identity checks passed');
}finally{globalThis.fetch=originalFetch}
