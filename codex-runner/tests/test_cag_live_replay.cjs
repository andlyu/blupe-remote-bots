const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture({live=true,storage=true}={}) {
  const nodes=[],timers=new Map(),stored=new Map();let interval=0,tracksStopped=0;
  class Node {
    constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.style={};this.listeners={};this.isConnected=true;nodes.push(this);}
    append(...children){for(const child of children){this.children.push(child);child.parentElement=this;}}
    after(child){this.parentElement?.append(child);}
    replaceChildren(...children){this.children=[];this.append(...children);}
    setAttribute(name,value){this[name]=value;}
    removeAttribute(name){delete this[name];}
    addEventListener(type,callback){(this.listeners[type]??=[]).push(callback);}
    fire(type,event={}){for(const fn of this.listeners[type]||[])fn(event);}
    showModal(){this.open=true;}
    close(){this.open=false;this.fire('close');}
    pause(){} load(){} play(){return Promise.resolve();}
    getContext(){return {drawImage(){},fillRect(){},fillText(){}};}
    captureStream(){return {getTracks(){return [{stop(){tracksStopped++;}}];}};}
  }
  const document={body:new Node('body'),createElement:tag=>new Node(tag),getElementById:id=>nodes.find(node=>node.id===id),addEventListener(){}};
  for(const id of ['myRunsList','cagStatus','runnerName','prompt','pastRunDialog']){const node=new Node('div');node.id=id;document.body.append(node);}
  document.getElementById('runnerName').value='Andrew';document.getElementById('prompt').value='Put box in bin';
  const source=new Node('canvas');source.width=640;source.height=360;source.dataset={frameSource:live?'video':'snapshot',presentedFrame:'1'};
  document.querySelector=()=>source;
  class Recorder extends Node {
    static isTypeSupported(type){return type.includes('webm');}
    start(){} stop(){queueMicrotask(()=>{this.fire('dataavailable',{data:new Blob(['real-camera-payload'],{type:'video/webm'})});this.fire('stop');});}
  }
  const idb={open(){const request={};queueMicrotask(()=>{
    if(!storage){request.error=new Error('storage unavailable');request.onerror();return;}
    request.result={transaction(name,mode){const transaction={objectStore(){return {
      put(clip){stored.set(clip.episode_id,clip);queueMicrotask(()=>transaction.oncomplete());},
      getAll(){const query={};queueMicrotask(()=>{query.result=[...stored.values()];query.onsuccess();});return query;}
    };}};return transaction;}};request.onsuccess();
  });return request;}};
  const window={MediaRecorder:Recorder,yamApplication:{sessionReady(){},modelDisplayName(){return 'MolmoAct2 + CAG-inspired guidance';}},yamReplayReview:{ready(){}}};
  vm.runInNewContext(fs.readFileSync('static/cag-live-replay.js','utf8'),{
    window,document,indexedDB:idb,MediaRecorder:Recorder,HTMLCanvasElement:Node,Blob,Date,Map,Set,Promise,URL:{createObjectURL(){return 'blob:test';},revokeObjectURL(){}},
    setInterval(fn){timers.set(++interval,fn);return interval;},clearInterval(id){timers.delete(id);}
  });
  const state={status:'running',session_id:'sess_test',episode_id:'ep_test',runner_name:'Andrew',provider:{approach:'MolmoAct2 + CAG-inspired guidance'},email:'private@example.com'};
  const tick=()=>{source.dataset.presentedFrame=String(Number(source.dataset.presentedFrame)+1);for(const fn of timers.values())fn();};
  return {window,document,source,stored,state,tick,stopped:()=>tracksStopped};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('retains real camera blob and actual runner/method, immediately opens replay and stores no email',async()=>{
  const f=fixture();f.window.cagLiveReplay.observe(f.state);f.tick();f.tick();
  f.window.cagLiveReplay.observe({...f.state,status:'timed_out'});await settle();
  const clip=f.stored.get('ep_test');assert(clip.blob.size>0);assert.equal(clip.unique_camera_frames,3);
  assert.equal(clip.runner_name,'Andrew');assert.match(clip.approach,/CAG/);assert(!('email' in clip));
  assert(f.document.getElementById('cagLiveReplayDialog').open);assert.equal(f.stopped(),1);
  assert.match(f.document.getElementById('cagReplayStatus').textContent,/ready/);
});
test('a startup still never becomes a claimed physical replay',async()=>{
  const f=fixture({live:false});f.window.cagLiveReplay.observe(f.state);f.tick();f.tick();
  f.window.cagLiveReplay.observe({...f.state,status:'stopped'});await settle();
  assert.equal(f.stored.size,0);assert(!f.document.getElementById('cagLiveReplayDialog').open);
});
test('unchanging live frame is rejected, and another session cannot stop this capture',async()=>{
  const f=fixture();f.window.cagLiveReplay.observe(f.state);
  f.window.cagLiveReplay.observe({...f.state,session_id:'somebody-else',status:'stopped'});await settle();assert.equal(f.stopped(),0);
  f.window.cagLiveReplay.observe({...f.state,status:'stopped'});await settle();
  assert.equal(f.stored.size,0);assert.match(f.document.getElementById('cagReplayStatus').textContent,/No usable/);
});
test('storage failure preserves immediate replay with honest recovery text',async()=>{
  const f=fixture({storage:false});f.window.cagLiveReplay.observe(f.state);f.tick();f.tick();
  f.window.cagLiveReplay.observe({...f.state,status:'stopped'});await settle();
  assert(f.document.getElementById('cagLiveReplayDialog').open);assert.equal(f.stored.size,0);
  assert.match(f.document.getElementById('cagReplayStatus').textContent,/Save video/);
});
