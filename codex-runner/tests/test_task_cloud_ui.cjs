const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(){
 const source=fs.readFileSync(path.join(__dirname,'../static/task-cloud.js'),'utf8');
 const window={devicePixelRatio:1},events={},draws=[],focused={};let queued;
 const ctx=new Proxy({measureText:text=>({width:text.length*7})},{get:(target,key)=>target[key]||((...args)=>draws.push([key,...args]))});
 const canvas={width:1000,height:540,clientWidth:1000,clientHeight:540,dataset:{},style:{},getContext:()=>ctx,
  addEventListener:(name,fn)=>events[name]=fn,setPointerCapture(){},getBoundingClientRect:()=>({left:0,top:0})};
 vm.runInNewContext(source,{window,ResizeObserver:class{observe(){}},requestAnimationFrame:fn=>{queued=fn;return 1}});
 const opened=[],cloud=window.yamTaskCloud.create(canvas,focused,run=>opened.push(run));
 const draw=()=>{queued?.();queued=null};
 return{cloud,canvas,events,opened,draw,focused,project:window.yamTaskCloud.project,offset:window.yamTaskCloud.offset,draws};
}
test('xyz rotation changes projected depth; persisted xyz is never changed; keyboard reaches duplicates',()=>{
 const c=setup(),xyz=[.1,.2,.3],rows=Array.from({length:5},(_,i)=>({episode_id:'ep_'+i,prompt:'Same task',xyz,assessment:{label:i%2?'Success':'Failure',eligibility:'included'}}));
 c.cloud.setRuns(rows);c.draw();assert.equal(c.canvas.dataset.renderedPoints,'5');
 assert.equal(c.canvas.dataset.camera,undefined,'Cloud metadata must not match the live [data-camera] selector');
 const initial=c.canvas.dataset.cloudCamera;c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();assert.notEqual(c.canvas.dataset.cloudCamera,initial);
 c.cloud.zoom(2);c.draw();assert.match(c.canvas.dataset.cloudCamera,/,2$/);c.cloud.reset();c.draw();assert.equal(c.canvas.dataset.cloudCamera,initial);
 for(let i=0;i<5;i++){c.cloud.open();c.cloud.step(1)}assert.equal(new Set(c.opened.map(run=>run.episode_id)).size,5);
 assert.deepEqual(xyz,[.1,.2,.3]);assert.notDeepEqual(c.offset('ep_0'),c.offset('ep_1'));
 const p=c.project([.2,.1,.5],0,0,1,1000,540),r=c.project([.2,.1,.5],1,1,1,1000,540);assert.notEqual(p.depth,r.depth);
});
test('display-scale rendering keeps every supplied attempt and uses shape and exclusion treatments',()=>{
 const c=setup(),rows=Array.from({length:10000},(_,i)=>({episode_id:'ep_'+i,prompt:'Task '+i,xyz:[(i%100)/200-.25,Math.floor(i/100)/200-.25,(i%13)/30-.2],assessment:{label:i%3===0?'Success':i%3===1?'Failure':null,eligibility:i%11===0?'excluded':'included'}}));
 c.cloud.setRuns(rows);c.draw();assert.equal(c.canvas.dataset.renderedPoints,'10000');
 assert.ok(c.draws.some(call=>call[0]==='arc'));assert.ok(c.draws.some(call=>call[0]==='rect'));assert.ok(c.draws.some(call=>call[0]==='lineTo'));
 c.cloud.setRuns([rows[0]],'ep_0');c.draw();assert.match(c.focused.textContent,/Task 0/);
 c.cloud.setRuns([]);c.draw();assert.match(c.focused.textContent,/No runs match/);
 c.cloud.setRuns([rows[0]],'ep_0');c.draw();assert.equal(c.canvas.dataset.renderedPoints,'1');assert.equal(c.canvas.dataset.cloudCamera,'-0.3,0.2,1');
});
