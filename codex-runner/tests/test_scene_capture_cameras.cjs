const test=require('node:test');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');
const modulePromise=import(pathToFileURL(path.resolve(__dirname,'../static/scene-capture-view.js')));
function setup(connect,options={}){
  let stamp=0,next=0;const timers=new Map();
  const panels=['left','top','right'].map(role=>{const sources=[],image={hidden:false};Object.defineProperty(image,'src',{set(value){sources.push(value);},get(){return sources.at(-1);}});return{role,image,label:{textContent:''},empty:{hidden:false,textContent:''},sources};});
  const instance=connect(panels,{now:()=>stamp,setTimer:(fn,delay)=>{const id=++next;timers.set(id,{fn,at:stamp+delay});return id;},clearTimer:id=>timers.delete(id),...options});
  function advance(ms){const end=stamp+ms;while(true){const entry=[...timers].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!entry)break;stamp=entry[1].at;timers.delete(entry[0]);entry[1].fn();}stamp=end;}
  return{panels,instance,advance,timers};
}
test('each native camera refreshes after its own completed request, without overlapping slow frames',async()=>{
  const {connectCameraPreviews}=await modulePromise;const f=setup(connectCameraPreviews);
  assert.deepEqual(f.panels.map(p=>p.sources.length),[1,1,1]);
  f.advance(1000);assert.deepEqual(f.panels.map(p=>p.sources.length),[1,1,1]);
  f.panels[0].image.onload();f.advance(1000);
  assert.deepEqual(f.panels.map(p=>p.sources.length),[2,1,1]);
  assert.match(f.panels[0].image.src,/cameras\/left\.jpg\?station=yam-1&t=2000$/);
});
test('camera failure is explicit and a later good frame restores the preview',async()=>{
  const {connectCameraPreviews}=await modulePromise;const f=setup(connectCameraPreviews),p=f.panels[1];
  p.image.onerror();assert.equal(p.image.hidden,true);assert.equal(p.empty.hidden,false);assert.match(p.label.textContent,/Unavailable/);
  f.advance(1000);p.image.onload();assert.equal(p.image.hidden,false);assert.equal(p.empty.hidden,true);assert.match(p.label.textContent,/Updated/);
});
test('a stalled camera times out and retries without freezing the other feeds',async()=>{
  const {connectCameraPreviews}=await modulePromise;const f=setup(connectCameraPreviews);
  f.panels[0].image.onload();f.advance(7000);assert.match(f.panels[1].label.textContent,/Unavailable/);
  f.advance(1000);assert.equal(f.panels[1].sources.length,2);assert.equal(f.panels[2].sources.length,2);
});
test('stopping previews cancels timers and does not make additional image requests',async()=>{
  const {connectCameraPreviews}=await modulePromise;const f=setup(connectCameraPreviews);f.instance.stop();f.advance(20000);
  assert.equal(f.timers.size,0);assert.deepEqual(f.panels.map(p=>p.sources.length),[1,1,1]);
});

test('health notifications announce only failure/recovery transitions, never periodic timestamps',async()=>{
  const {connectCameraPreviews}=await modulePromise,events=[];const f=setup(connectCameraPreviews,{onHealthChange:roles=>events.push(roles)}),p=f.panels[0];
  p.image.onload();f.advance(1000);p.image.onload();assert.deepEqual(events,[]);
  f.advance(1000);p.image.onerror();assert.deepEqual(events,[['left']]);
  f.advance(1000);p.image.onerror();assert.deepEqual(events,[['left']]);
  f.advance(1000);p.image.onload();assert.deepEqual(events,[['left'],[]]);
});
