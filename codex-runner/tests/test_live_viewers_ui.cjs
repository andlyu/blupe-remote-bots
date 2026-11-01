const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/live-viewers.js'),'utf8');

function setup() {
  let now=0,tick;
  const badge={hidden:true},label={textContent:''},doc={hidden:false};
  const viewer={isConnected:true,getBoundingClientRect:()=>({top:10,left:0,bottom:490,right:640,width:640,height:480})};
  const listeners={};
  const viewport={innerWidth:1440,innerHeight:900,setInterval(fn){tick=fn;return 1},clearInterval(){},
    addEventListener:(name,fn)=>listeners[name]=fn,removeEventListener:name=>delete listeners[name]};
  const context={window:viewport};vm.createContext(context);vm.runInContext(source,context);
  const counter=viewport.yamLiveViewers.create({badge,label,viewer,doc,viewport,clock:()=>now});
  return {counter,badge,label,doc,viewer,listeners,tick:()=>tick(),advance:ms=>now+=ms};
}

test('only visible live-camera views send a heartbeat',()=>{
  const s=setup();assert.equal(s.counter.watching(),true);
  s.doc.hidden=true;assert.equal(s.counter.watching(),false);
  s.doc.hidden=false;
  s.viewer.getBoundingClientRect=()=>({top:-490,left:0,bottom:-10,right:640,width:640,height:480});
  assert.equal(s.counter.watching(),false,'Scrolling to history is not live watching');
  s.viewer.getBoundingClientRect=()=>({top:1000,left:0,bottom:1480,right:640,width:640,height:480});
  assert.equal(s.counter.watching(),false);
  s.viewer.isConnected=false;assert.equal(s.counter.watching(),false);
});

test('unknown and stale counts hide instead of showing a fabricated zero',()=>{
  const s=setup();assert.equal(s.badge.hidden,true);
  s.counter.render(2);assert.equal(s.label.textContent,'2 watching live');assert.equal(s.badge.hidden,false);
  s.advance(29999);s.tick();assert.equal(s.badge.hidden,false);
  s.advance(1);s.tick();assert.equal(s.badge.hidden,true);
  s.counter.render(0);assert.equal(s.label.textContent,'0 watching live');assert.equal(s.badge.hidden,false);
  for(const value of [undefined,null,-1,1.5,'7',NaN,Infinity]) {
    s.counter.render(1);s.counter.render(value);assert.equal(s.badge.hidden,true);
  }
});

test('robot switching and page exit immediately hide the previous count',()=>{
  const s=setup();s.counter.render(5);s.counter.reset();assert.equal(s.badge.hidden,true);
  s.counter.render(1);s.listeners.pagehide();assert.equal(s.badge.hidden,true);
  s.counter.close();assert.equal(s.listeners.pagehide,undefined);
});
