const test=require('node:test');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const modulePromise=import(pathToFileURL(path.resolve(__dirname,'../static/scene-capture-view.js')));
function setup(connect,{hlsSupported=true,nativeHls=false}={}){
  let stamp=0,next=0;const timers=new Map(),frames=new Map(),images=[],streams=[],events=[],listeners={};
  function canvas(){const draws=[];return{width:640,height:360,hidden:true,dataset:{},draws,getContext:()=>({drawImage:(...args)=>draws.push(args)})};}
  const panels=['left','top','right'].map(role=>({role,canvas:canvas(),label:{textContent:''},empty:{hidden:false}}));
  const video={paused:true,readyState:0,currentTime:0,videoWidth:2560,videoHeight:1080,
    canPlayType(){return nativeHls?'probably':'';},seekable:{length:1,start:()=>1,end:()=>10},setAttribute(){},removeAttribute(){},load(){this.readyState=0;},pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},remove(){this.removed=true;}};
  const document={hidden:false,body:{append(){}},addEventListener:(k,v)=>listeners[k]=v,removeEventListener:k=>delete listeners[k]};
  class Hls{
    static Events={ERROR:'error',MANIFEST_PARSED:'manifest'};static isSupported(){return hlsSupported;}
    constructor(config){this.events={};this.config=config;streams.push(this);}
    on(k,v){this.events[k]=v;}loadSource(url){this.url=url;}attachMedia(v){this.video=v;}
    destroy(){this.destroyed=true;}emit(k,data){this.events[k]?.(null,data);}
  }
  const instance=connect(panels,{Hls,document,createVideo:()=>video,createCanvas:canvas,createImage:()=>{const i={naturalWidth:640,naturalHeight:360,removeAttribute(){}};images.push(i);return i;},
    now:()=>stamp,setTimer:(fn,delay)=>{const id=++next;timers.set(id,{fn,at:stamp+delay});return id;},clearTimer:id=>timers.delete(id),
    requestFrame:fn=>{const id=++next;frames.set(id,fn);return id;},cancelFrame:id=>frames.delete(id),onHealthChange:state=>events.push(state)});
  function advance(ms){const end=stamp+ms;while(true){const entry=[...timers].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!entry)break;stamp=entry[1].at;timers.delete(entry[0]);entry[1].fn();}stamp=end;}
  function paint(time){video.readyState=4;video.paused=false;video.currentTime=time;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn());}
  return{panels,instance,advance,paint,timers,frames,images,streams,video,events,document,visibility:()=>listeners.visibilitychange()};
}
test('reference HD atlas and four-camera fallback map all three roles correctly',async()=>{
  const {cameraCrop}=await modulePromise;
  assert.deepEqual(['left','top','right'].map(r=>cameraCrop(r,2560,1080)),[[1920,0,640,360],[1920,360,640,360],[1920,720,640,360]]);
  assert.deepEqual(['left','top','right'].map(r=>cameraCrop(r,1280,720)),[[640,0,640,360],[0,360,640,360],[640,360,640,360]]);
});
test('one continuous decoder paints synchronized role crops and stops startup snapshots',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews);
  assert.equal(f.streams.length,1);assert.match(f.streams[0].url,/video\/synchronized-hd\/index.m3u8$/);
  assert.equal(f.images.length,3);f.paint(1);
  assert.deepEqual(f.panels.map(p=>p.canvas.dataset.presentedFrame),['1','1','1']);
  const draws=f.panels.map(p=>p.canvas.draws.at(-1));assert.equal(draws[0][0],draws[2][0]);
  assert.deepEqual(draws.map(d=>d.slice(1,5)),[[1920,0,640,360],[1920,360,640,360],[1920,720,640,360]]);
  assert.ok(f.images.every(i=>i.onload===null));
  f.advance(3000);f.paint(2);assert.equal(f.images.length,3);assert.equal(f.streams.length,1);
  assert.ok(f.panels.every(p=>p.label.textContent==='Live video · delayed'));
});
test('snapshot failure retains the last actual frame and never claims stills are live',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews),p=f.panels[0];
  f.images[0].onload();assert.equal(p.canvas.hidden,false);assert.match(p.label.textContent,/Still image/);
  const last=p.canvas.draws.at(-1);f.advance(5000);f.images[3].onerror();
  assert.equal(p.canvas.draws.at(-1),last);assert.equal(p.canvas.hidden,false);assert.equal(p.empty.hidden,true);
  assert.match(p.label.textContent,/Still image · received 5 s ago/);assert.doesNotMatch(p.label.textContent,/Live/);
});
test('fatal errors reconnect once with bounded retry; ordinary segment errors do not tear down playback',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews),first=f.streams[0];f.paint(1);
  first.emit('error',{fatal:false});assert.equal(first.destroyed,undefined);assert.equal(f.streams.length,1);
  first.emit('error',{fatal:true});first.emit('error',{fatal:true});assert.equal(first.destroyed,true);
  assert.ok(f.panels.every(p=>p.canvas.hidden===false&&/Video stalled/.test(p.label.textContent)));
  f.advance(1000);assert.equal(f.streams.length,2);
  first.emit('error',{fatal:true});assert.equal(f.streams[1].destroyed,undefined);
  f.paint(2);assert.equal(f.events.at(-1),'live');
});
test('stalled media is labelled honestly, gets still fallback, and reconnects after the full startup window',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews);f.paint(1);
  f.advance(4000);assert.match(f.panels[0].label.textContent,/Video stalled · received 4 s ago/);
  assert.equal(f.images.length,6);assert.equal(f.streams.length,1);
  f.advance(16000);assert.equal(f.streams[0].destroyed,true);f.advance(1000);assert.equal(f.streams.length,2);
  f.paint(3);assert.ok(f.panels.every(p=>p.label.textContent==='Live video · delayed'));
});
test('a recovering stream advances without watchdog reconnects or extra snapshot requests',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews);
  for(let i=1;i<=65;i++){f.advance(1000);f.paint(i);}
  assert.equal(f.streams.length,1);assert.equal(f.images.length,3);
  assert.deepEqual(f.events,['live']);assert.equal(f.panels[2].canvas.dataset.presentedFrame,'65');
});
test('hidden tabs release video and resume automatically without clearing retained frames',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews);f.paint(1);
  f.document.hidden=true;f.visibility();f.advance(30000);
  assert.equal(f.streams.length,1);assert.equal(f.streams[0].destroyed,true);assert.match(f.panels[0].label.textContent,/paused/);
  assert.equal(f.panels[0].canvas.hidden,false);f.document.hidden=false;f.visibility();assert.equal(f.streams.length,2);f.paint(2);assert.equal(f.events.at(-1),'live');
});
test('stop cancels reconnect, fallback, watchdog and paint callbacks',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews);f.instance.stop();f.advance(60000);
  assert.equal(f.timers.size,0);assert.equal(f.frames.size,0);assert.equal(f.streams.length,1);assert.equal(f.video.removed,true);
});

test('native HLS uses the same stream and catches up within its live window',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews,{hlsSupported:false,nativeHls:true});
  assert.equal(f.streams.length,0);assert.match(f.video.src,/video\/synchronized-hd\/index.m3u8$/);
  f.video.onloadedmetadata();assert.equal(f.video.currentTime,9.5);f.paint(9.6);
  assert.ok(f.panels.every(p=>p.canvas.dataset.frameSource==='video'));
  f.instance.stop();assert.equal(f.video.onprogress,null);assert.equal(f.timers.size,0);
});
test('still fallback waits for its own request and uses a bounded retry interval',async()=>{
  const {connectCameraPreviews}=await modulePromise,f=setup(connectCameraPreviews,{hlsSupported:false});
  assert.equal(f.images.length,3);f.advance(4000);assert.equal(f.images.length,3);
  f.images[0].onerror();f.advance(4000);assert.equal(f.images.length,3);
  f.advance(1000);assert.equal(f.images.length,4);f.instance.stop();
});
