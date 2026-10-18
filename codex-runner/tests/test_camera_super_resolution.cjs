const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(__dirname+'/../static/super-resolution/viewer.js','utf8');
function harness({gpu=true}={}){
  const workers=[],nodes=[],callbacks=new Map(),events={};let now=1000,id=0,raf;
  class Node{
    constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.listeners={};this.isConnected=true;nodes.push(this);}
    append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}
    remove(){this.isConnected=false;if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(x=>x!==this);}
    setAttribute(k,v){this.attrs[k]=v;}
    addEventListener(k,fn){this.listeners[k]=fn;}
    getContext(){return {drawImage(){}};}
    closest(){return this.parentElement;}
  }
  const picture=new Node('picture'),source=new Node('source');picture.append(source);
  source.width=640;source.height=360;source.dataset={frameSource:'video',presentedFrame:'1'};
  const container={querySelector:()=>source};
  const document={hidden:false,body:new Node('body'),fullscreenElement:container,
    createElement:tag=>new Node(tag),querySelector:()=>null,addEventListener:(k,fn)=>events[k]=fn};
  class Worker{constructor(){this.sent=[];workers.push(this);}postMessage(x){this.sent.push(x);}terminate(){this.terminated=true;}emit(data){this.onmessage({data});}}
  const context={document,navigator:{gpu:gpu?{}:undefined},performance:{now:()=>now},
    localStorage:{getItem:()=>null,setItem(){}},Worker,MutationObserver:class{observe(){}disconnect(){}},
    requestAnimationFrame:fn=>{raf=fn;return 1;},cancelAnimationFrame(){raf=null;},
    setTimeout:fn=>{callbacks.set(++id,fn);return id;},clearTimeout:i=>callbacks.delete(i),
    createImageBitmap:async()=>({close(){this.closed=true;}})};
  context.window={Worker,OffscreenCanvas:class{},createImageBitmap:context.createImageBitmap,addEventListener:(k,fn)=>events[k]=fn};
  vm.runInNewContext(code,context);
  return {source,picture,document,workers,events,nodes,
    get button(){return nodes.find(x=>x.tag==='button');},get overlay(){return nodes.find(x=>x.tag==='canvas');},
    get status(){return nodes.find(x=>x.tag==='span');},
    async paint(ms=125){now+=ms;source.dataset.presentedFrame=String(Number(source.dataset.presentedFrame)+1);raf?.();await Promise.resolve();},
    get now(){return now;}};
}
test('one in-flight inference skips newer inputs without queuing',async()=>{
  const h=harness(),w=h.workers[0];w.emit({type:'ready'});
  await h.paint();await h.paint();await h.paint();
  assert.equal(w.sent.filter(x=>x.type==='frame').length,1);
  const bitmap={close(){this.closed=true;}};
  w.emit({type:'frame',bitmap,started:h.now,elapsed:25,width:1280,height:720,sequence:1});
  assert(bitmap.closed);assert.equal(h.overlay.hidden,false);
  await h.paint();assert.equal(w.sent.filter(x=>x.type==='frame').length,2);
});
test('turning enhancement off terminates inference and leaves source video intact',async()=>{
  const h=harness(),w=h.workers[0];w.emit({type:'ready'});await h.paint();
  h.button.listeners.click();
  assert(w.terminated);assert.equal(h.overlay.hidden,true);assert.equal(h.button.attrs['aria-pressed'],'false');
  assert.equal(h.source.dataset.frameSource,'video');
  const bitmap={close(){this.closed=true;}};
  w.emit({type:'frame',bitmap,started:h.now,elapsed:20,width:1280,height:720});
  assert(bitmap.closed);assert.equal(h.overlay.hidden,true);
});
test('stale results are discarded and repeated slow processing returns to original',async()=>{
  const h=harness(),w=h.workers[0];w.emit({type:'ready'});
  for(let i=0;i<3;i++){
    await h.paint();const bitmap={close(){this.closed=true;}};
    w.emit({type:'frame',bitmap,started:h.now-250,elapsed:220,width:1280,height:720});assert(bitmap.closed);
  }
  assert(w.terminated);assert.match(h.status.textContent,/too slow/);assert(h.overlay.hidden);
});
test('exiting or hiding the expanded view disposes GPU work',()=>{
  for(const hide of [false,true]){
    const h=harness();if(hide){h.document.hidden=true;h.events.visibilitychange();}
    else{h.document.fullscreenElement=null;h.events.fullscreenchange();}
    assert(h.workers[0].terminated);assert.equal(h.overlay.isConnected,false);
  }
});
test('unsupported browsers keep the original video without starting a worker',()=>{
  const h=harness({gpu:false});assert.equal(h.workers.length,0);
  assert(h.button.disabled);assert.match(h.status.textContent,/unavailable/);assert(h.overlay.hidden);
});
