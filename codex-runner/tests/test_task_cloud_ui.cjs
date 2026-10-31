const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(labeler){
 const source=fs.readFileSync(path.join(__dirname,'../static/task-cloud.js'),'utf8');
 const window={devicePixelRatio:1,...(labeler?{yamRunLabels:{outcome:labeler}}:{})},events={},draws=[],focused={};let queued;
 const ctx=new Proxy({createRadialGradient(){return {addColorStop(){}}},measureText:text=>({width:text.length*7}),fill(){draws.push(['fill',this.fillStyle])},stroke(){draws.push(['stroke',this.strokeStyle])}},{get:(target,key)=>target[key]||((...args)=>draws.push([key,...args]))});
 const canvas={width:1000,height:540,clientWidth:1000,clientHeight:540,dataset:{},style:{},getContext:()=>ctx,
  addEventListener:(name,fn)=>events[name]=fn,setPointerCapture(){},getBoundingClientRect:()=>({left:0,top:0})};
 vm.runInNewContext(source,{window,ResizeObserver:class{observe(){}},requestAnimationFrame:fn=>{queued=fn;return 1}});
 const opened=[],previews=[],cloud=window.yamTaskCloud.create(canvas,focused,run=>opened.push(run),(run,point)=>previews.push({run,point}));
 const draw=()=>{queued?.();queued=null};
 return{cloud,canvas,events,opened,draw,focused,project:window.yamTaskCloud.project,offset:window.yamTaskCloud.offset,draws,previews,outcome:window.yamTaskCloud.outcome,regionsFor:window.yamTaskCloud.regionsFor};
}
test('neighborhoods require five binary labels, ignore uncertain/unknown outcomes and preserve 3D separation',()=>{
 const c=setup(run=>run.testOutcome),rows=[];
 function add(count,state,xyz){for(let i=0;i<count;i++)rows.push({episode_id:'ep_'+rows.length,prompt:'Task',xyz,testOutcome:state})}
 add(6,'Success',[0,0,-.3]);add(2,'Failure',[0,0,-.3]);add(40,'Unscored',[0,0,-.3]);add(3,'Uncertain',[0,0,-.3]);
 add(6,'Failure',[0,0,.3]);add(1,'Success',[0,0,.3]);
 add(4,'Success',[.4,0,0]);add(3,'Success',[-.4,0,0]);add(3,'Failure',[-.4,0,0]);
 const result=c.regionsFor(rows);
 assert.equal(result.regions.length,2);
 const green=result.regions.find(r=>r.label==='Success');assert.equal(green.total,8);assert.equal(green.Success,6);assert.equal(green.Uncertain,3);assert.equal(green.Unscored,40);
 const red=result.regions.find(r=>r.label==='Failure');assert.equal(red.total,7);assert.equal(red.Failure,6);
 assert.equal(JSON.stringify(c.regionsFor(rows.slice().reverse()).regions),JSON.stringify(result.regions),'row order must not move regions');
 assert.deepEqual(rows[0].xyz,[0,0,-.3]);
});
test('highlight controls preserve individual runs, 3D support under rotation, source recalculation and replay selection',()=>{
 const c=setup(),rows=Array.from({length:6},(_,i)=>({episode_id:'ep_h'+i,prompt:'Lift',xyz:[0,0,0],assessment:{label:i===0?'Failure':'Success',eligibility:'included'}}));
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.draw();
 assert.equal(c.canvas.dataset.renderedPoints,'6');assert.equal(c.canvas.dataset.highlightRegions,'1');assert.match(c.cloud.highlightSummary(),/1 success-heavy/);assert.match(c.focused.textContent,/Nearby: 5 Success \/ 1 Failure/);
 c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();assert.equal(c.canvas.dataset.highlightRegions,'1');
 c.cloud.open();assert.equal(c.opened[0].episode_id,'ep_h0');
 c.cloud.setHighlight('failure');c.draw();assert.equal(c.canvas.dataset.highlightRegions,'0');assert.match(c.cloud.highlightSummary(),/No areas meet/);
 c.cloud.setHighlight('none');c.draw();assert.equal(c.canvas.dataset.highlightRegions,'0');assert.match(c.cloud.highlightSummary(),/off/);assert.equal(c.canvas.dataset.renderedPoints,'6');
 c.cloud.setRuns(rows.slice(0,4));c.cloud.setHighlight('both');c.draw();assert.equal(c.canvas.dataset.highlightRegions,'0','filtering to four runs must remove stale highlight');
 c.cloud.setRuns(rows.map(r=>({...r,assessment:{label:'Failure',eligibility:'included'}})));c.draw();assert.match(c.cloud.highlightSummary(),/1 failure-heavy/);
});
test('highlight picker updates the existing Cloud and remembers the choice without fetching new runs',async()=>{
 const c=require('./helpers/past-runs.cjs')('', 'cloud');
 c.cloud.setHighlight=mode=>{c.cloud.highlight=mode};c.cloud.highlightSummary=()=>`Region mode: ${c.cloud.highlight}`;
 c.events['blupe-robot-selected']({detail:'yam-1'});c.answer(c.requests[0],[{episode_id:'ep_a',prompt:'Lift',xyz:[0,0,0]}]);await c.flush();
 assert.equal(c.cloud.highlight,'both');const before=c.cloud.rows;
 c.nodes.get('taskCloudHighlight').value='success';c.nodes.get('taskCloudHighlight').emit('change');
 assert.equal(c.cloud.highlight,'success');assert.equal(c.cloud.rows,before);assert.equal(c.requests.length,1);
 assert.equal(c.nodes.get('taskCloudRegionStatus').textContent,'Region mode: success');assert.equal(c.storage.get('yam-cloud-highlight'),'success');
});
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
test('display-scale rendering keeps every supplied attempt and uses green/red dots and identical hollow unscored treatment',()=>{
 const c=setup(),rows=Array.from({length:10000},(_,i)=>({episode_id:'ep_'+i,prompt:'Task '+i,xyz:[(i%100)/200-.25,Math.floor(i/100)/200-.25,(i%13)/30-.2],assessment:{label:i%3===0?'Success':i%3===1?'Failure':null,eligibility:i%11===0?'excluded':'included'}}));
 c.cloud.setRuns(rows);c.draw();assert.equal(c.canvas.dataset.renderedPoints,'10000');
 assert.ok(c.draws.some(call=>call[0]==='arc'));assert.ok(!c.draws.some(call=>call[0]==='rect'));assert.ok(c.draws.some(call=>call[0]==='lineTo'));
 assert.ok(c.draws.some(call=>call[0]==='fill' && call[1]==='#246744'));assert.ok(c.draws.some(call=>call[0]==='fill' && call[1]==='#b2352c'));
 const excluded={assessment:{label:'Success',eligibility:'excluded'}},unlabeled={assessment:{label:null,eligibility:'unlabeled'}};
 assert.equal(c.outcome(excluded),'Unscored');assert.equal(c.outcome(unlabeled),'Unscored');
 c.cloud.setRuns([{...rows[0],...excluded}]);c.draw();const excludedFills=c.draws.filter(call=>call[0]==='fill').at(-1);
 c.cloud.setRuns([{...rows[0],...unlabeled}]);c.draw();assert.deepEqual(c.draws.filter(call=>call[0]==='fill').at(-1),excludedFills);
 assert.equal(excluded.assessment.label,'Success');
 assert.equal(c.outcome({assessment:{label:'Success',eligibility:'included'}}),'Success');
 assert.equal(c.outcome({assessment:{label:'Failure',eligibility:'included'}}),'Failure');
 c.cloud.setRuns([rows[0]],'ep_0');c.draw();assert.match(c.focused.textContent,/Task 0/);
 c.cloud.setRuns([]);c.draw();assert.match(c.focused.textContent,/No runs match/);
 c.cloud.setRuns([rows[0]],'ep_0');c.draw();assert.equal(c.canvas.dataset.renderedPoints,'1');assert.equal(c.canvas.dataset.cloudCamera,'-0.3,0.2,1');
});

test('pointer and keyboard previews track the point, clear on exit/drag/reset, and preserve click replay',()=>{
 const c=setup(),run={episode_id:'ep_hover',prompt:'Hover task',xyz:[0,0,0]};
 c.cloud.setRuns([run]);c.draw();
 const xyz=c.offset(run.episode_id),p=c.project(xyz,-.3,.2,1,1000,540);
 const pointer={clientX:p.x,clientY:p.y,pointerType:'mouse',pointerId:1};
 c.events.pointermove(pointer);assert.equal(c.previews.at(-1).run,run);assert.equal(c.previews.at(-1).point.x,p.x);
 c.events.pointermove({...pointer,clientX:0,clientY:0});assert.match(c.focused.textContent,/Hover task/);assert.equal(c.previews.at(-1).run,null);
 c.events.pointerleave();assert.equal(c.previews.at(-1).run,null);
 c.events.focus();assert.equal(c.previews.at(-1).run,run);
 c.events.keydown({key:'Escape'});assert.equal(c.previews.at(-1).run,null);
 c.events.pointermove({...pointer,pointerType:'touch'});assert.equal(c.previews.at(-1).run,null);
 c.events.pointerdown(pointer);assert.equal(c.previews.at(-1).run,null);
 c.events.pointerup(pointer);assert.equal(c.opened.at(-1),run);
 c.cloud.step(1);assert.equal(c.previews.at(-1).run,run);
 c.cloud.setRuns([]);assert.equal(c.previews.at(-1).run,null);
});
