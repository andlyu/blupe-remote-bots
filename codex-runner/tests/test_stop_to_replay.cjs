const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const all=fs.readFileSync(process.env.REPLAY_HISTORY_SOURCE||path.join(__dirname,'../static/replay-history.js'),'utf8');
const source=all.slice(all.indexOf('/* Personal public-run history'));
function setup(){
 const nodes=new Map(),events={},requests=[],timers=new Map(),opened=[];let seq=0,clock=10000;
 const element=()=>({dataset:{},listeners:{},children:[],hidden:false,open:false,value:'',parentElement:{hidden:false},
  addEventListener(n,f){(this.listeners[n]||=[]).push(f)},emit(n){for(const f of this.listeners[n]||[])f({})},
  append(...x){this.children.push(...x)},replaceChildren(){this.children=[]},after(){},remove(){},pause(){},load(){},removeAttribute(){},
  showModal(){this.open=true},close(){this.open=false;this.emit('close')},scrollIntoView(){},focus(){}});
 const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 const window={addEventListener(n,f){events[n]=f},history:{replaceState(){}},yamRunSidebar:{open(){get('pastRunDialog').open=true}},
  yamReplayHistory:{openRun(run){opened.push(run);window.yamReplayReview.ready()},refresh(){}}};
 const document={body:{dataset:{postRunReplay:'auto'}},visibilityState:'visible',getElementById:get,createElement:element};
 vm.runInNewContext(source,{window,document,location:{search:'',href:'https://playground.blupe.io/'},URL,URLSearchParams,
  Date:{now:()=>clock},renderRunMetrics(){},renderStepMetricsChart(){},
  setTimeout(f,ms){timers.set(++seq,{f,ms});return seq},clearTimeout(id){timers.delete(id)},
  fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))}});
 events['blupe-robot-selected']({detail:'robot-ba8413962083809c'});
 const observe=status=>window.yamReplayReview.observe({session_id:'sess_own',episode_id:'ep_own',status},'robot-ba8413962083809c','csrf');
 const answer=(r,runs=[])=>r.resolve({ok:true,json:async()=>({runs})});
 const flush=()=>new Promise(setImmediate);
 return {nodes,get,document,requests,timers,opened,events,observe,answer,flush,setClock(v){clock=v}};
}
test('Stop opens replay and checks the local cache before terminal status arrives',async()=>{
 const c=setup();c.observe('running');c.get('stop').emit('click');
 assert.equal(c.get('pastRunDialog').open,true);
 const first=c.requests.find(r=>r.url.includes('episode_id=ep_own'));
 assert.ok(first.url.endsWith('&preview=1'));
 c.answer(first);await c.flush();
 assert.equal([...c.timers.values()].at(-1).ms,200);
 c.setClock(16000);[...c.timers.values()].at(-1).f();
 const next=c.requests.at(-1);assert.ok(next.url.endsWith('&preview=1'),'keep first-media checks independent of catalog');
 c.answer(next,[{episode_id:'ep_own',robot_id:'robot-ba8413962083809c',video_url:'/media.mp4',video_duration_s:7.5,video_quality:'quick'}]);await c.flush();
 assert.equal(c.opened.length,1);
 const lookups=c.requests.filter(r=>r.url.includes('episode_id=')).length;
 c.observe('stopped');c.observe('stopped');
 assert.equal(c.requests.filter(r=>r.url.includes('episode_id=')).length,lookups,'later status must not restart playback');
});
test('closing replay invalidates a late readiness response',async()=>{
 const c=setup();c.observe('running');c.get('stop').emit('click');
 const request=c.requests.find(r=>r.url.includes('episode_id='));c.get('pastRunDialog').close();
 c.answer(request,[{episode_id:'ep_own',robot_id:'robot-ba8413962083809c',video_url:'/media.mp4',video_duration_s:2}]);await c.flush();
 assert.equal(c.opened.length,0);
});
test('a paused deployment keeps its existing opt-out',()=>{
 const c=setup();c.document.body.dataset.postRunReplay='paused';c.observe('running');c.get('stop').emit('click');
 assert.equal(c.get('pastRunDialog').open,false);
});
