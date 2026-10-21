const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/replay-progress.js'),'utf8');
function setup({readyState='complete',lateDependencies=false}={}){
  const nodes={},events={},documentEvents={},requests=[],timers=new Map(),opened=[];let clock=1000,tid=0;
  function element(){return {listeners:{},children:[],hidden:false,open:true,paused:false,currentTime:1,ended:false,src:'',
    setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]},append(...x){this.children.push(...x)},after(x){nodes[x.id]=x},
    addEventListener(n,f){(this.listeners[n]??=[]).push(f)},emit(n){for(const f of this.listeners[n]||[])f()},
    parentElement:{after(x){nodes[x.id]=x}}};}
  for(const id of ['pastRunVideo','pastRunDialog','replayProcessing','robotSelector'])nodes[id]=element();
  nodes.robotSelector.value='robot';
  const window={addEventListener(n,f){events[n]=f}};
  const dependencies=()=>Object.assign(window,{yamReplayReview:{observe(){}},yamReplayHistory:{openRun(run){opened.push(run)}}});
  if(!lateDependencies)dependencies();
  vm.runInNewContext(source,{window,document:{readyState,addEventListener(n,f){documentEvents[n]=f},getElementById:id=>nodes[id],createElement:element},
    location:{search:''},URLSearchParams,Date:{now:()=>clock},setTimeout(f){timers.set(++tid,f);return tid},clearTimeout:id=>timers.delete(id),
    fetch(url,options){return new Promise(resolve=>requests.push({url,options,resolve}))},encodeURIComponent});
  const flush=()=>new Promise(setImmediate);
  const answer=(request,runs)=>request.resolve({ok:true,json:async()=>({runs})});
  const observe=status=>window.yamReplayReview.observe({session_id:'mine',episode_id:'ep_mine',status},'robot','csrf');
  const run=(quality='quick')=>({episode_id:'ep_mine',robot_id:'robot',video_url:'/api/quick-replays/video',video_sha256:quality,video_quality:quality,video_duration_s:3});
  return {nodes,events,requests,timers,opened,window,flush,answer,observe,run,dependencies,domReady(){documentEvents.DOMContentLoaded?.()},advance(ms){clock+=ms},tick(){const [id,f]=[...timers][0];timers.delete(id);f()}};
}
test('deferred scripts can finish installing replay dependencies before progress attaches',async()=>{
  const c=setup({readyState:'interactive',lateDependencies:true});
  assert.equal(c.nodes.replayProgress,undefined);
  c.dependencies();c.domReady();c.observe('running');c.observe('stopped');
  assert.match(c.requests[0].url,/preview=1/);
  c.answer(c.requests[0],[c.run()]);await c.flush();
  assert.equal(c.opened[0].video_quality,'quick');
});
test('own completed run polls the direct path and displays a playable quick preview',async()=>{
  const c=setup();c.observe('running');c.observe('stopped');
  assert.match(c.requests[0].url,/preview=1/);
  assert.equal(c.nodes.replayProcessing.hidden,true);
  c.answer(c.requests[0],[c.run()]);await c.flush();
  assert.equal(c.opened.length,1);assert.equal(c.opened[0].video_quality,'quick');
  assert.equal(c.requests.length,2);
});
test('final edit waits for playback to end rather than interrupting the viewer',async()=>{
  const c=setup();c.window.yamReplayHistory.openRun(c.run());
  c.answer(c.requests[0],[c.run('final')]);await c.flush();
  assert.equal(c.opened.length,1);
  assert.match(c.nodes.replayProgress.children[1].textContent,/after playback ends/);
  c.nodes.pastRunVideo.emit('ended');
  assert.equal(c.opened.length,2);assert.equal(c.opened[1].video_quality,'final');
  assert.equal(c.nodes.replayProgress.hidden,true);
});
test('opening an already-final immutable source does not leave an improvement countdown',async()=>{
  const c=setup();c.window.yamReplayHistory.openRun(c.run('final'));
  c.nodes.pastRunVideo.src='/api/quick-replays/ep_mine/'+'a'.repeat(64)+'.mp4';
  c.nodes.pastRunVideo.emit('loadstart');
  c.answer(c.requests[0],[{...c.run('final'),video_sha256:'a'.repeat(64)}]);await c.flush();
  assert.equal(c.nodes.replayProgress.hidden,true);assert.equal(c.timers.size,0);
});
test('closing or changing robot discards late readiness responses',async()=>{
  for(const change of ['close','robot']){
    const c=setup();c.observe('running');c.observe('stopped');
    if(change==='close'){c.nodes.pastRunDialog.open=false;c.nodes.pastRunDialog.emit('close')}
    else c.events['blupe-robot-selected']();
    c.answer(c.requests[0],[c.run()]);await c.flush();
    assert.equal(c.opened.length,0);assert.equal(c.timers.size,0);
  }
});
test('waiting has indeterminate progress and checks the published catalog at a bounded interval',async()=>{
  const c=setup();c.observe('running');c.observe('stopped');
  c.answer(c.requests[0],[]);await c.flush();c.advance(6000);c.tick();
  const [bar,text]=c.nodes.replayProgress.children;
  assert.match(text.textContent,/Waiting for saved replay/);assert.equal(bar.value,undefined);
  assert.doesNotMatch(text.textContent,/Finishing|seconds left/);
  assert.doesNotMatch(c.requests[1].url,/preview=1/);
  c.answer(c.requests[1],[c.run('final')]);await c.flush();
  assert.equal(c.opened[0].video_quality,'final');
});
test('reopening a processing recording keeps waiting and a failed check is visible',async()=>{
  const c=setup();c.window.yamReplayHistory.openRun({...c.run(),video_url:null,video_status:'processing'});
  assert.equal(c.requests.length,1);
  c.requests[0].resolve({ok:false});await c.flush();
  assert.match(c.nodes.replayProgress.children[1].textContent,/status unavailable/);
  assert.equal(c.timers.size,1);
});
