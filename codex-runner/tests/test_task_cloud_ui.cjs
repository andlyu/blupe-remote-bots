const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function setup(labeler,interactive=false){
 const source=fs.readFileSync(path.join(__dirname,'../static/task-cloud.js'),'utf8');
 const window={devicePixelRatio:1,...(labeler?{yamRunLabels:{outcome:labeler,describe:labeler}}:{})},events={},draws=[],focused={};let queued;
 const ctx=new Proxy({createRadialGradient(){return {addColorStop(){}}},measureText:text=>({width:text.length*7}),fill(){draws.push(['fill',this.fillStyle])},stroke(){draws.push(['stroke',this.strokeStyle])}},{get:(target,key)=>target[key]||((...args)=>draws.push([key,...args]))});
 const canvas={width:1000,height:540,clientWidth:1000,clientHeight:540,dataset:{},style:{},getContext:()=>ctx,
  addEventListener:(name,fn)=>events[name]=fn,setPointerCapture(){},getBoundingClientRect:()=>({left:0,top:0})};
 vm.runInNewContext(source,{window,ResizeObserver:class{observe(){}},requestAnimationFrame:fn=>{queued=fn;return 1}});
 const doc={activeElement:null,createElement(tag){return {tag,children:[],listeners:{},dataset:{},style:{},hidden:false,attributes:{},ownerDocument:doc,
  append(...items){for(const item of items)item.parent=this;this.children.push(...items)},addEventListener(name,fn){this.listeners[name]=fn},emit(name,event={}){this.listeners[name]?.({...event,target:event.target || this})},setAttribute(name,value){this.attributes[name]=value},contains(node){return node===this || this.children.includes(node)},closest(selector){return selector==='button' && this.tag==='button'?this:null},remove(){this.removed=true},focus(){doc.activeElement=this}}}};
 const captionRoot=interactive?doc.createElement('div'):null;canvas.focus=()=>{doc.activeElement=canvas};
 const opened=[],previews=[],areas=[],cloud=window.yamTaskCloud.create(canvas,focused,run=>opened.push(run),(run,point)=>previews.push({run,point}),()=>{},area=>areas.push(area),captionRoot);
 const draw=()=>{queued?.();queued=null};
 return{cloud,canvas,events,opened,draw,focused,areas,captionRoot,doc,volumeContains:window.yamTaskCloud.volumeContains,volumeCorners:window.yamTaskCloud.volumeCorners,worldCoordinates:window.yamTaskCloud.worldCoordinates,cameraCoordinates:window.yamTaskCloud.cameraCoordinates,summarizeArea:window.yamTaskCloud.summarizeArea,project:window.yamTaskCloud.project,offset:window.yamTaskCloud.offset,draws,previews,outcome:window.yamTaskCloud.outcome,regionsFor:window.yamTaskCloud.regionsFor};
}
test('area summary separates unknown outcomes and chooses an actual median task across all selected attempts',()=>{
 const c=setup(run=>run.testOutcome),rows=[
  {episode_id:'a',prompt:'Left task',xyz:[-.4,0,0],testOutcome:'Success'},
  {episode_id:'b',prompt:'Middle task',xyz:[.1,0,0],testOutcome:'Failure'},
  {episode_id:'c',prompt:'Middle task',xyz:[.1,0,0],testOutcome:'Uncertain'},
  {episode_id:'d',prompt:'Right task',xyz:[.7,0,0],testOutcome:'Unscored'}];
 const summary=c.summarizeArea(rows);
 assert.equal(summary.total,4);assert.equal(summary.Success,1);assert.equal(summary.Failure,1);assert.equal(summary.Uncertain,1);assert.equal(summary.Unscored,1);
 assert.equal(summary.scored,2);assert.equal(summary.successRate,.5);assert.equal(summary.medianPrompt,'Middle task');
 assert.equal(c.summarizeArea(rows.slice().reverse()).medianPrompt,summary.medianPrompt);
 assert.equal(c.summarizeArea(rows.slice(2)).successRate,null);assert.equal(c.summarizeArea([]).medianPrompt,'');
});
test('3D box excludes overlapping points outside its depth; resizing changes membership while rotation and source changes preserve geometry',()=>{
 const c=setup(run=>run.testOutcome),rows=[-.4,0,.4].map((depth,i)=>({episode_id:'ep_volume'+i,robot_id:'yam-1',prompt:'Depth '+depth,xyz:c.worldCoordinates([0,0,depth],-.3,.2),testOutcome:['Failure','Success','Uncertain'][i]}));
 rows.push({episode_id:'outside',robot_id:'yam-1',prompt:'Outside',xyz:c.worldCoordinates([.8,0,0],-.3,.2),testOutcome:'Failure'});
 c.cloud.setRuns(rows);c.draw();const initialCamera=c.canvas.dataset.cloudCamera;
 const start={pointerId:1,pointerType:'mouse',clientX:470,clientY:245},end={...start,clientX:530,clientY:295};
 c.cloud.setAreaSelection(true);c.events.pointerdown(start);c.events.pointermove(end);c.events.pointerup(end);c.draw();
 assert.equal(c.areas.at(-1).total,1);assert.equal(c.areas.at(-1).Success,1);assert.equal(c.areas.at(-1).successRate,1);assert.equal(c.opened.length,0);
 assert.deepEqual(Array.from(c.cloud.getSelectedRuns(),run=>run.episode_id),['ep_volume1']);
 assert.equal(c.canvas.dataset.cloudCamera,initialCamera,'creation preserves the current camera');assert.equal(c.areas.at(-1).active,false,'background drag immediately rotates after drawing');
 const volume=c.canvas.dataset.volumeBox;c.cloud.zoom(1.5);c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();
 assert.equal(c.canvas.dataset.volumeBox,volume);assert.equal(c.canvas.dataset.areaSelected,'1');
 c.cloud.setVolumeDimension('depth',300);c.draw();assert.equal(c.areas.at(-1).total,3);assert.equal(c.areas.at(-1).successRate,.5);assert.equal(c.areas.at(-1).Uncertain,1);
 c.cloud.setRuns(rows.map(run=>({...run,testOutcome:'Failure'})));c.draw();assert.equal(c.areas.at(-1).Failure,3);assert.equal(c.areas.at(-1).successRate,0);
 c.cloud.setVolumeDimension('position',0);c.draw();assert.equal(c.areas.at(-1).total,2,'depth position shifts finite volume, not just its camera');
 c.cloud.setRuns(rows.slice(1));c.draw();assert.equal(c.areas.at(-1).total,1);
 c.cloud.setRuns(rows.map(run=>({...run,robot_id:'other'})));c.draw();assert.equal(c.areas.at(-1).hasSelection,false);assert.equal(c.areas.at(-1).total,0);assert.equal(c.canvas.dataset.volumeBox,'');assert.equal(c.cloud.getSelectedRuns().length,0);
});
test('volume axes round-trip camera coordinates and contain only real persisted coordinates within all six faces',()=>{
 const c=setup(),local=[.2,-.3,.4],world=c.worldCoordinates(local,.7,-.3),back=c.cameraCoordinates(world,.7,-.3);
 local.forEach((v,i)=>assert.ok(Math.abs(v-back[i])<1e-12));
 const axes=[[1,0,0],[0,1,0],[0,0,1]].map(a=>c.worldCoordinates(a,.7,-.3)),volume={center:world,axes,half:[.1,.2,.3]};
 assert.equal(c.volumeContains(volume,world),true);
 assert.equal(c.volumeCorners(volume).length,8);for(const point of c.volumeCorners(volume))assert.equal(c.volumeContains(volume,point),true);
 for(let axis=0;axis<3;axis++)for(const sign of [-1,1])assert.equal(c.volumeContains(volume,world.map((v,i)=>v+axes[axis][i]*(volume.half[axis]+.001)*sign)),false);
});
test('face handles resize one boundary while retaining the opposite face and preserving replays',()=>{
 const c=setup(),rows=[{episode_id:'center',prompt:'Center',xyz:[0,0,0]}];c.cloud.setRuns(rows);c.draw();c.cloud.setAreaSelection(true);
 const start={pointerId:1,pointerType:'mouse',clientX:440,clientY:220},end={...start,clientX:560,clientY:320};
 c.events.pointerdown(start);c.events.pointermove(end);c.events.pointerup(end);c.draw();
 const before=JSON.parse(c.canvas.dataset.volumeBox),handle=JSON.parse(c.canvas.dataset.volumeHandles).find(h=>h.name==='X' && h.sign===1),camera=c.canvas.dataset.cloudCamera.split(',').map(Number),center=c.project(before.center,...camera,1000,540);
 const down={...start,clientX:handle.x,clientY:handle.y},up={...down,clientX:handle.x+(handle.x-center.x)*.5,clientY:handle.y+(handle.y-center.y)*.5};
 c.events.pointerdown(down);c.events.pointermove(up);c.events.pointerup(up);c.draw();
 const after=JSON.parse(c.canvas.dataset.volumeBox);assert.ok(after.half[0]>before.half[0]);for(let i=0;i<3;i++)assert.ok(Math.abs((after.center[i]-after.axes[0][i]*after.half[0])-(before.center[i]-before.axes[0][i]*before.half[0]))<1e-9,'opposite face stays fixed');assert.deepEqual(after.axes,before.axes);assert.equal(c.opened.length,0);assert.deepEqual(rows[0].xyz,[0,0,0]);
});
test('Add3D box is immediate and moving/rotating the object changes membership independently of camera views',()=>{
 const c=setup(run=>run.testOutcome),rows=Array.from({length:10},(_,i)=>({episode_id:'x'+i,prompt:'X task',xyz:[i%2?-.18:.18,0,0],testOutcome:'Success'}));
 rows.push({episode_id:'y',prompt:'Y task',xyz:[0,.18,0],testOutcome:'Failure'});
 c.cloud.setRuns(rows);c.cloud.addVolume();c.draw();assert.equal(c.areas.at(-1).total,10);assert.equal(c.areas.at(-1).successRate,1);assert.equal(c.areas.at(-1).active,false);
 const initialBox=JSON.parse(c.canvas.dataset.volumeBox),camera=c.canvas.dataset.cloudCamera;
 c.cloud.setVolumeTool('move');c.cloud.nudgeVolume(0,1);c.draw();assert.equal(c.areas.at(-1).total,5);assert.equal(c.canvas.dataset.cloudCamera,camera);assert.deepEqual(JSON.parse(c.canvas.dataset.volumeBox).axes,initialBox.axes);
 c.cloud.addVolume();c.draw();c.cloud.rotateVolume(2,Math.PI/2);c.draw();assert.equal(c.areas.at(-1).total,1);assert.equal(c.areas.at(-1).Failure,1);assert.equal(c.areas.at(-1).successRate,0);assert.equal(c.canvas.dataset.cloudCamera,camera);
 const rotated=c.canvas.dataset.volumeBox;c.cloud.setView('front');c.draw();assert.equal(c.canvas.dataset.volumeBox,rotated);assert.notEqual(c.canvas.dataset.cloudCamera,camera);assert.equal(c.areas.at(-1).total,1);
 for(const [key,tool] of [['w','move'],['e','rotate'],['r','resize']]){c.events.keydown({key,preventDefault(){}});assert.equal(c.areas.at(-1).tool,tool)}
 assert.equal(c.opened.length,0);assert.deepEqual(rows.at(-1).xyz,[0,.18,0]);
});
test('adding or drawing a box preserves the existing non-default camera and zoom',()=>{
 const c=setup();c.cloud.setRuns([{episode_id:'a',prompt:'Task',xyz:[0,0,0]}]);c.cloud.zoom(1.8);c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();
 const camera=c.canvas.dataset.cloudCamera;c.cloud.addVolume();c.draw();assert.equal(c.canvas.dataset.cloudCamera,camera);
 c.cloud.setAreaSelection(true);const a={pointerId:1,pointerType:'mouse',clientX:400,clientY:200},b={...a,clientX:600,clientY:350};c.events.pointerdown(a);c.events.pointermove(b);c.events.pointerup(b);c.draw();assert.equal(c.canvas.dataset.cloudCamera,camera);assert.equal(c.opened.length,0);
});
test('rotation ring uses its actual3D plane; Escape restores the full original transform',()=>{
 const c=setup();c.cloud.setRuns([{episode_id:'a',prompt:'Task',xyz:[0,0,0]}]);c.cloud.addVolume();c.cloud.setVolumeTool('rotate');c.draw();
 const before=c.canvas.dataset.volumeBox,camera=c.canvas.dataset.cloudCamera,ring=JSON.parse(c.canvas.dataset.volumeHandles).find(h=>h.name==='Z');
 const a=ring.samples[35],b=ring.samples[43],start={pointerId:1,pointerType:'mouse',clientX:a.x,clientY:a.y},end={...start,clientX:b.x,clientY:b.y};
 c.events.pointerdown(start);c.events.pointermove(end);c.draw();assert.notEqual(c.canvas.dataset.volumeBox,before);assert.equal(c.canvas.dataset.cloudCamera,camera);
 const changed=JSON.parse(c.canvas.dataset.volumeBox),original=JSON.parse(before);assert.deepEqual(changed.center,original.center);assert.deepEqual(changed.half,original.half);
 for(const axis of changed.axes)assert.ok(Math.abs(axis.reduce((n,v)=>n+v*v,0)-1)<1e-9);
 c.events.keydown({key:'Escape'});c.draw();assert.equal(c.canvas.dataset.volumeBox,before);assert.equal(c.opened.length,0);
});
test('keyboard area controls apply, cancel and clear while leaving default camera keys intact',()=>{
 const c=setup(run=>run.testOutcome),rows=Array.from({length:6},(_,i)=>({episode_id:'ep_key'+i,prompt:'Center task',xyz:[0,0,0],testOutcome:i%2?'Success':'Failure'}));
 c.cloud.setRuns(rows);c.draw();const camera=c.canvas.dataset.cloudCamera;
 c.cloud.setAreaSelection(true);c.events.keydown({key:'ArrowRight',preventDefault(){}});c.events.keydown({key:'ArrowRight',shiftKey:true,preventDefault(){}});c.events.keydown({key:'Enter',preventDefault(){}});c.draw();
 assert.equal(c.areas.at(-1).total,6);assert.equal(c.opened.length,0);assert.equal(c.canvas.dataset.cloudCamera,camera);
 c.cloud.setAreaSelection(true);
 c.events.keydown({key:'ArrowDown',preventDefault(){}});assert.equal(c.areas.at(-1).drawing,true);c.events.keydown({key:'Escape'});assert.equal(c.areas.at(-1).drawing,false);assert.equal(c.areas.at(-1).total,6);
 c.cloud.setAreaSelection(false);c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();assert.notEqual(c.canvas.dataset.cloudCamera,camera);assert.equal(c.areas.at(-1).total,6);
 c.cloud.clearArea();c.draw();assert.equal(c.areas.at(-1).hasSelection,false);assert.equal(c.canvas.dataset.areaSelected,'0');
});
test('touch pinch and canceled gestures do not commit a stale selection or open a video',()=>{
 const c=setup(),run={episode_id:'ep_touch',prompt:'Task',xyz:[0,0,0]};c.cloud.setRuns([run]);c.draw();c.cloud.setAreaSelection(true);
 const a={pointerId:1,pointerType:'touch',clientX:450,clientY:240},b={pointerId:2,pointerType:'touch',clientX:550,clientY:300};
 c.events.pointerdown(a);c.events.pointerdown(b);c.events.pointermove({...b,clientX:580});c.events.pointerup(a);c.events.pointerup(b);c.draw();
 assert.equal(c.areas.at(-1).hasSelection,false);assert.equal(c.opened.length,0);
 c.events.pointerdown(a);c.events.pointermove(b);c.events.pointercancel();c.events.pointerup(a);assert.equal(c.areas.at(-1).drawing,false);assert.equal(c.opened.length,0);
});
test('area controls expose the binary denominator, label source and empty state without loading more runs',async()=>{
 const c=require('./helpers/past-runs.cjs')('', 'cloud');
 const area={total:10,Success:1,Failure:2,Uncertain:3,Unscored:4,scored:3,successRate:1/3,medianPrompt:'Actual central task',hasSelection:true,drawing:false,volume:{width:100,height:90,depth:50,position:40}};
 c.cloud.setAreaSelection=active=>c.cloud.areaChange({...area,active});
 c.cloud.clearArea=()=>c.cloud.areaChange({...area,total:0,hasSelection:false,active:true});
 c.events['blupe-robot-selected']({detail:'yam-1'});c.answer(c.requests[0],[{episode_id:'ep_a',prompt:'Lift',xyz:[0,0,0]}]);await c.flush();
 c.nodes.get('taskCloudSelectArea').emit('click');
 assert.equal(c.nodes.get('taskCloudSelectArea').getAttribute('aria-pressed'),'true');assert.equal(c.nodes.get('taskCloudAreaSummary').hidden,false);assert.equal(c.nodes.get('taskCloudTransformToolbar').hidden,false);
 assert.match(c.nodes.get('taskCloudAreaRate').textContent,/33\.3% of 3 Success\/Failure labels/);assert.match(c.nodes.get('taskCloudAreaCounts').textContent,/10 runs selected/);
 assert.equal(c.nodes.get('taskCloudAreaPrompt').textContent,'Actual central task');
 const changed=[];c.cloud.setVolumeDimension=(...args)=>changed.push(args);
 assert.equal(c.nodes.get('taskCloudVolumeDepth').value,'50');c.nodes.get('taskCloudVolumeDepth').value='200';c.nodes.get('taskCloudVolumeDepth').emit('input');assert.deepEqual(changed,[['depth',200]]);assert.equal(c.requests.length,1);
 const tools=[];c.cloud.setVolumeTool=tool=>tools.push(tool);c.cloud.nudgeVolume=(axis,direction)=>tools.push([axis,direction]);
 c.nodes.get('taskCloudToolRotate').emit('click');c.nodes.get('taskCloudNudgeZPlus').emit('click');assert.deepEqual(tools,['rotate',[2,1]]);
 c.nodes.get('pastRunsLabelSource').value='human';c.nodes.get('pastRunsLabelSource').emit('change');
 c.cloud.areaChange({...area,Success:0,Failure:0,Uncertain:0,Unscored:10,scored:0,successRate:null,active:true});
 assert.match(c.nodes.get('taskCloudAreaRate').textContent,/No Success\/Failure labels.*Human-labeled/);assert.equal(c.requests.length,1);
 c.nodes.get('taskCloudClearArea').emit('click');assert.equal(c.nodes.get('taskCloudAreaSummary').hidden,true);assert.equal(c.nodes.get('taskCloudClearArea').disabled,true);assert.equal(c.nodes.get('taskCloudTransformToolbar').hidden,true);
});
test('area captions are opt-in and zoom does not cover runs with individual task labels',()=>{
 const c=setup(run=>run.testOutcome),prompt='Unobstructed task';c.cloud.setRuns(Array.from({length:6},(_,i)=>({episode_id:'plain'+i,prompt,xyz:[0,0,0],testOutcome:'Failure'})));c.cloud.setHighlight('both');c.draw();
 assert.equal(c.canvas.dataset.areaLabels,'false');assert.equal(c.canvas.dataset.highlightRegions,'1');assert.ok(!c.draws.some(call=>call[0]==='fillText' && /Failure:|Unobstructed/.test(call[1])));
 c.cloud.zoom(3);c.draws.length=0;c.draw();assert.ok(!c.draws.some(call=>call[0]==='fillText' && /Failure:|Unobstructed/.test(call[1])));
 c.cloud.setAreaLabels(true);c.draws.length=0;c.draw();assert.equal(c.canvas.dataset.areaLabels,'true');assert.ok(!c.draws.some(call=>call[0]==='fillText' && call[1]==='Failure: 6/6'),'Zoomed-close captions stay hidden even when enabled');
 c.cloud.zoom(1/3);c.draw();assert.ok(c.draws.some(call=>call[0]==='fillText' && call[1]==='Failure: 6/6'));assert.match(c.focused.textContent,/Median failure prompt/);
});
test('neighborhoods require five binary labels, ignore uncertain/unknown outcomes and preserve 3D separation',()=>{
 const c=setup(run=>run.testOutcome),rows=[];
 function add(count,state,xyz){for(let i=0;i<count;i++)rows.push({episode_id:'ep_'+rows.length,prompt:'Task',xyz,testOutcome:state})}
 add(6,'Success',[0,0,-.3]);add(2,'Failure',[0,0,-.3]);add(40,'Unscored',[0,0,-.3]);add(3,'Uncertain',[0,0,-.3]);
 add(6,'Failure',[0,0,.3]);add(1,'Success',[0,0,.3]);
 add(4,'Success',[.4,0,0]);add(3,'Success',[-.4,0,0]);add(3,'Failure',[-.4,0,0]);
 const result=c.regionsFor(rows);
 assert.equal(result.regions.length,2);
 const green=result.regions.find(r=>r.label==='Success');assert.equal(green.total,8);assert.equal(green.Success,6);assert.equal(green.Uncertain,3);assert.equal(green.Unscored,40);
 assert.equal(green.representativePrompt,'Task');
 const red=result.regions.find(r=>r.label==='Failure');assert.equal(red.total,7);assert.equal(red.Failure,6);
 assert.equal(JSON.stringify(c.regionsFor(rows.slice().reverse()).regions),JSON.stringify(result.regions),'row order must not move regions');
 assert.deepEqual(rows[0].xyz,[0,0,-.3]);
});
test('highlight controls preserve individual runs, 3D support under rotation, source recalculation and replay selection',()=>{
 const c=setup(),rows=Array.from({length:6},(_,i)=>({episode_id:'ep_h'+i,prompt:'Lift',xyz:[0,0,0],assessment:{label:i===0?'Failure':'Success',eligibility:'included'}}));
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();
 assert.equal(c.canvas.dataset.renderedPoints,'6');assert.equal(c.canvas.dataset.highlightRegions,'1');assert.match(c.cloud.highlightSummary(),/1 success-heavy/);assert.match(c.focused.textContent,/Nearby: 5 Success \/ 1 Failure/);
 c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();assert.equal(c.canvas.dataset.highlightRegions,'1');
 c.cloud.open();assert.equal(c.opened[0].episode_id,'ep_h0');
 c.cloud.setHighlight('failure');c.cloud.setAreaLabels(true);c.draw();assert.equal(c.canvas.dataset.highlightRegions,'0');assert.match(c.cloud.highlightSummary(),/No areas meet/);
 c.cloud.setHighlight('none');c.draw();assert.equal(c.canvas.dataset.highlightRegions,'0');assert.match(c.cloud.highlightSummary(),/off/);assert.equal(c.canvas.dataset.renderedPoints,'6');
 c.cloud.setRuns(rows.slice(0,4));c.cloud.setHighlight('both');c.draw();assert.equal(c.canvas.dataset.highlightRegions,'0','filtering to four runs must remove stale highlight');
 c.cloud.setRuns(rows.map(r=>({...r,assessment:{label:'Failure',eligibility:'included'}})));c.draw();assert.match(c.cloud.highlightSummary(),/1 failure-heavy/);
});
test('failure areas show the observed failed prompt nearest the repeated-attempt coordinate median',()=>{
 const c=setup(run=>run.testOutcome),rows=[];
 const add=(count,state,x,prompt)=>{for(let i=0;i<count;i++)rows.push({episode_id:'ep_'+String(rows.length).padStart(3,'0'),prompt,xyz:[x,0,0],testOutcome:state})};
 add(1,'Failure',-.03,'Left task');add(4,'Failure',.02,'Pick up the poker chip');add(1,'Failure',.06,'Right task');
 add(1,'Success',0,'Successful task');add(30,'Uncertain',-.03,'Uncertain task');add(30,'Unscored',-.03,'Unknown task');
 add(8,'Failure',.5,'Distant task');
 const result=c.regionsFor(rows),region=result.regions.find(region=>region.xyz[0]<.1);
 assert.equal(region.representativePrompt,'Pick up the poker chip');assert.equal(region.Failure,6);assert.equal(region.total,7);
 assert.equal(JSON.stringify(c.regionsFor(rows.slice().reverse()).regions),JSON.stringify(result.regions));
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();
 assert.ok(c.draws.some(call=>call[0]==='fillText' && call[1]==='Pick up the poker chip'));
 assert.match(c.focused.textContent,/Median failure prompt: Pick up the poker chip/);
 const noPrompts=c.regionsFor(rows.map(run=>({...run,prompt:''})));assert.equal(noPrompts.regions.find(region=>region.xyz[0]<.1).representativePrompt,'');
});
test('success captions use successful attempts even when a failed task shares the median position',()=>{
 const c=setup(run=>run.testOutcome),rows=[
  {episode_id:'z_left',prompt:'Left successful task',xyz:[-.03,0,0],testOutcome:'Success'},
  ...Array.from({length:3},(_,i)=>({episode_id:'s_'+i,prompt:'Lift the bottle',xyz:[.02,0,0],testOutcome:'Success'})),
  {episode_id:'z_right',prompt:'Right successful task',xyz:[.06,0,0],testOutcome:'Success'},
  {episode_id:'a_failed',prompt:'Drop the bottle',xyz:[.02,0,0],testOutcome:'Failure'}];
 const region=c.regionsFor(rows).regions.find(region=>region.label==='Success');assert.equal(region.Success,5);assert.equal(region.total,6);assert.equal(region.representativePrompt,'Lift the bottle');
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();assert.match(c.focused.textContent,/Median success prompt: Lift the bottle/);
 assert.ok(c.draws.some(call=>call[0]==='fillText' && call[1]==='Lift the bottle'));
});
test('long failure prompts wrap and truncate inside mobile canvas bounds without changing region counts',()=>{
 const c=setup(run=>run.testOutcome),prompt='Pick up the poker chip and carefully move it to the cup '.repeat(8);
 c.canvas.clientWidth=320;c.canvas.clientHeight=360;
 c.cloud.setRuns(Array.from({length:6},(_,i)=>({episode_id:'ep_'+i,prompt,xyz:[0,0,0],testOutcome:'Failure'})));
 c.cloud.setHighlight('failure');c.cloud.setAreaLabels(true);c.draw();
 const label=c.draws.find(call=>call[0]==='fillText' && call[1]==='Failure: 6/6');assert.ok(label);
 const promptLines=c.draws.filter(call=>call[0]==='fillText' && /Pick|…/.test(call[1]));
 assert.equal(promptLines.length,2);assert.match(promptLines[1][1],/…$/);
 for(const call of promptLines){assert.ok(call[2]>=4);assert.ok(call[2]+call[1].length*7<=320-4)}
 assert.match(c.focused.textContent,new RegExp(prompt.slice(0,40)));
});
test('combined phone labels retain success and failure captions when their default positions collide',()=>{
 const c=setup(run=>run.testOutcome);c.canvas.clientWidth=320;c.canvas.clientHeight=360;
 const rows=['Success','Failure'].flatMap((testOutcome,index)=>Array.from({length:5},(_,i)=>({episode_id:`ep_${index}_${i}`,prompt:index?'Place blue block on the tray':'Place green block on the towel',xyz:index?[.07,0,.1]:[-.07,0,-.1],testOutcome})));
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();
 assert.ok(c.draws.some(call=>call[0]==='fillText' && call[1]==='Success: 5/5'));
 assert.ok(c.draws.some(call=>call[0]==='fillText' && call[1]==='Failure: 5/5'));
 assert.equal(c.canvas.dataset.highlightRegions,'2');assert.equal(c.canvas.dataset.renderedPoints,'10');
 for(const call of c.draws.filter(call=>call[0]==='strokeRect')){assert.ok(call[1]>=4 && call[2]>=4);assert.ok(call[1]+call[3]<=316 && call[2]+call[4]<=356)}
});
test('independent outcome checkboxes retain all four saved modes without fetching new runs',async()=>{
 for(const saved of ['both','success','failure','none']) {
  const c=require('./helpers/past-runs.cjs')('', 'cloud',saved);
  c.cloud.setHighlight=mode=>{c.cloud.highlight=mode};c.cloud.highlightSummary=()=>`Region mode: ${c.cloud.highlight}`;
  const success=c.nodes.get('taskCloudSuccessAreas'),failure=c.nodes.get('taskCloudFailureAreas');
  assert.equal(success.checked,['both','success'].includes(saved));assert.equal(failure.checked,['both','failure'].includes(saved));
  c.events['blupe-robot-selected']({detail:'yam-1'});c.answer(c.requests[0],[{episode_id:'ep_a',prompt:'Lift',xyz:[0,0,0]}]);await c.flush();
  assert.equal(c.cloud.highlight,saved);const before=c.cloud.rows;
  for(const [green,red,mode] of [[true,false,'success'],[false,true,'failure'],[false,false,'none'],[true,true,'both']]) {
   success.checked=green;failure.checked=red;success.emit('change');
   assert.equal(c.cloud.highlight,mode);assert.equal(c.cloud.rows,before);assert.equal(c.requests.length,1);
   assert.equal(c.storage.get('yam-cloud-highlight'),mode);assert.equal(c.nodes.get('taskCloudRegionStatus').textContent,`Region mode: ${mode}`);
  }
 }
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

function captionFixture(interactive=false) {
 const c=setup(run=>run.testOutcome,interactive),rows=[
  {episode_id:'left',robot_id:'yam-1',prompt:'Left failed task',xyz:[-.03,0,0],testOutcome:'Failure'},
  ...Array.from({length:4},(_,i)=>({episode_id:'median_'+i,robot_id:'yam-1',prompt:'Lift the bottle',xyz:[.02,0,0],testOutcome:'Failure'})),
  {episode_id:'right',robot_id:'yam-1',prompt:'Right failed task',xyz:[.06,0,0],testOutcome:'Failure'},
  {episode_id:'a_success',robot_id:'yam-1',prompt:'Other outcome at the median',xyz:[.02,0,0],testOutcome:'Success'}];
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();
 const box=()=>JSON.parse(c.canvas.dataset.areaCaptions)[0];
 const pointer=(pointerType='mouse')=>{const b=box();return {pointerId:1,pointerType,clientX:b.x+b.w/2,clientY:b.y+b.h/2}};
 return {...c,rows,box,pointer};
}
test('clicking or tapping an area caption opens its actual matching-outcome median run without moving the camera',()=>{
 for(const pointerType of ['mouse','touch']) {
  const c=captionFixture(),camera=c.canvas.dataset.cloudCamera,point=c.pointer(pointerType);
  assert.equal(c.box().episodeId,'median_0');assert.equal(c.regionsFor(c.rows.slice().reverse()).regions[0].representativeRun.episode_id,'median_0');
  c.events.pointerdown(point);c.events.pointermove({...point,clientX:point.clientX+1});c.events.pointerup(point);c.draw();
  assert.equal(c.opened.length,1);assert.equal(c.opened[0].episode_id,'median_0');assert.equal(c.opened[0].testOutcome,'Failure');assert.equal(c.opened[0].prompt,'Lift the bottle');
  assert.equal(c.canvas.dataset.cloudCamera,camera);
 }
});
test('caption visibility follows projected depth and returns on zoom out while preserving tints and points',()=>{
 const c=setup(run=>run.testOutcome),rows=['near','far'].flatMap((name,index)=>Array.from({length:5},(_,i)=>({episode_id:name+i,prompt:name,xyz:[0,0,index?.5:-.5],testOutcome:'Success'})));
 c.cloud.setRuns(rows);c.cloud.setHighlight('success');c.cloud.setAreaLabels(true);c.draw();assert.equal(JSON.parse(c.canvas.dataset.areaCaptions).length,2);
 c.cloud.zoom(3);c.draw();const captions=JSON.parse(c.canvas.dataset.areaCaptions);assert.equal(captions.length,1);assert.equal(captions[0].episodeId,'far0');
 assert.equal(c.canvas.dataset.renderedPoints,'10');assert.equal(c.canvas.dataset.highlightRegions,'2');
 c.cloud.zoom(1/3);c.draw();assert.equal(JSON.parse(c.canvas.dataset.areaCaptions).length,2);
});
test('caption dragging, cancellation and hidden or filtered release never open a stale median run',()=>{
 for(const change of ['drag','cancel','zoom','filter','labels','highlight']) {
  const c=captionFixture(),point=c.pointer();c.events.pointerdown(point);
  if(change==='drag')c.events.pointermove({...point,clientX:point.clientX+40});
  if(change==='cancel')c.events.pointercancel();
  if(change==='zoom')c.cloud.zoom(3);
  if(change==='filter')c.cloud.setRuns([]);
  if(change==='labels')c.cloud.setAreaLabels(false);
  if(change==='highlight')c.cloud.setHighlight('none');
  c.draw();c.events.pointerup(point);assert.equal(c.opened.length,0,change);
 }
});
test('caption hover previews its median and keeps keyboard/open controls on that run',()=>{
 const c=captionFixture(),point=c.pointer();c.events.pointermove(point);c.draw();
 assert.equal(c.canvas.style.cursor,'pointer');assert.match(c.focused.textContent,/Lift the bottle/);
 assert.equal(c.previews.at(-1).run.episode_id,'median_0');
 c.events.keydown({key:'Enter',preventDefault(){}});assert.equal(c.opened[0].episode_id,'median_0');
});

test('idle dot and keyboard previews work while drawing is armed and after a box is selected',()=>{
 for(const mode of ['draw','selected']) {
  const c=setup(),run={episode_id:'ep_hover_box',prompt:'Hover with box',xyz:[0,0,0]};
  c.cloud.setRuns([run]);c.draw();c.cloud.setAreaSelection(true);
  if(mode==='selected'){c.events.keydown({key:'Enter',preventDefault(){}});c.draw();}
  const camera=c.canvas.dataset.cloudCamera,box=c.canvas.dataset.volumeBox;
  const p=c.project(c.offset(run.episode_id),-.3,.2,1,1000,540),pointer={clientX:p.x,clientY:p.y,pointerType:'mouse',pointerId:1};
  c.events.pointermove(pointer);assert.equal(c.previews.at(-1).run,run,mode);
  c.events.pointerleave();assert.equal(c.previews.at(-1).run,null);
  c.events.focus();assert.equal(c.previews.at(-1).run,run,mode+' keyboard');
  c.draw();assert.equal(c.canvas.dataset.cloudCamera,camera);assert.equal(c.canvas.dataset.volumeBox,box);
  c.events.pointerdown(pointer);assert.equal(c.previews.at(-1).run,null,'active gesture hides preview');
  c.events.pointermove({...pointer,clientX:p.x+20});assert.equal(c.previews.at(-1).run,null);
  c.events.pointercancel();
 }
});

test('View runs in the box uses the current selection and disables empty boxes',()=>{
 const c=require('./helpers/past-runs.cjs')('', 'cloud'),opened=[];
 let selected=[{episode_id:'ep_selected',robot_id:'yam-1',prompt:'Selected task'}];
 c.cloud.getSelectedRuns=()=>selected;c.window.yamRunSidebar={openSelection:rows=>opened.push(rows.slice())};
 const area={hasSelection:true,total:1,Success:1,Failure:0,Uncertain:0,Unscored:0,scored:1,successRate:1,medianPrompt:'Selected task'};
 c.cloud.areaChange(area);const button=c.nodes.get('taskCloudViewAreaRuns');assert.equal(button.disabled,false);
 button.emit('click');assert.equal(opened[0][0].episode_id,'ep_selected');
 selected=[{episode_id:'ep_after_resize',robot_id:'yam-1'}];button.emit('click');assert.equal(opened[1][0].episode_id,'ep_after_resize','reads geometry at click time');
 selected=[];c.cloud.areaChange({...area,total:0,scored:0,successRate:null});assert.equal(button.disabled,true);button.emit('click');assert.equal(opened.length,2);
 c.cloud.areaChange({...area,hasSelection:false,total:0,successRate:null});assert.equal(button.disabled,true);
});

test('Hide box removes the overlay and handles while preserving exact geometry, runs and camera',()=>{
 const c=setup(),rows=[{episode_id:'ep_inside',robot_id:'yam-1',prompt:'Inside',xyz:[0,0,0]},{episode_id:'ep_outside',robot_id:'yam-1',prompt:'Outside',xyz:[1,1,1]}];
 c.cloud.setRuns(rows);c.draw();c.cloud.setAreaSelection(true);c.events.keydown({key:'Enter',preventDefault(){}});c.draw();
 const box=c.canvas.dataset.volumeBox,camera=c.canvas.dataset.cloudCamera,selected=Array.from(c.cloud.getSelectedRuns(),r=>r.episode_id),handles=JSON.parse(c.canvas.dataset.volumeHandles);
 assert.equal(c.canvas.dataset.boxVisible,'true');assert.ok(handles.length>0);
 c.cloud.setBoxVisible(false);c.draw();assert.equal(c.canvas.dataset.boxVisible,'false');assert.equal(c.canvas.dataset.volumeBox,box);assert.equal(c.canvas.dataset.cloudCamera,camera);assert.equal(c.canvas.dataset.volumeHandles,'[]');assert.deepEqual(Array.from(c.cloud.getSelectedRuns(),r=>r.episode_id),selected);assert.equal(c.areas.at(-1).boxVisible,false);
 c.events.pointermove({pointerId:1,pointerType:'mouse',clientX:handles[0].x,clientY:handles[0].y});assert.notEqual(c.canvas.style.cursor,'ew-resize','hidden handles cannot intercept dot hover');
 c.cloud.setBoxVisible(true);c.draw();assert.equal(c.canvas.dataset.boxVisible,'true');assert.equal(c.canvas.dataset.volumeBox,box);assert.equal(c.canvas.dataset.cloudCamera,camera);assert.ok(JSON.parse(c.canvas.dataset.volumeHandles).length>0);
 c.cloud.setBoxVisible(false);c.cloud.setAreaSelection(true);c.events.keydown({key:'Enter',preventDefault(){}});c.draw();assert.equal(c.canvas.dataset.boxVisible,'true','drawing a new box makes it visible');
 c.cloud.clearArea();c.draw();assert.equal(c.canvas.dataset.boxVisible,'false');assert.equal(c.cloud.getSelectedRuns().length,0);
});
test('Hide and Show use visibility state while View runs remains enabled for a hidden selection',()=>{
 const c=require('./helpers/past-runs.cjs')('', 'cloud'),changes=[];c.cloud.setBoxVisible=value=>changes.push(value);c.window.yamRunSidebar={openSelection(){}};
 const area={hasSelection:true,total:1,Success:1,Failure:0,Uncertain:0,Unscored:0,scored:1,successRate:1,boxVisible:true};
 c.cloud.areaChange(area);const hide=c.nodes.get('taskCloudHideArea');assert.equal(hide.disabled,false);assert.equal(hide.textContent,'Hide box');hide.emit('click');assert.equal(changes.at(-1),false);
 c.cloud.areaChange({...area,boxVisible:false});assert.equal(hide.textContent,'Show box');assert.equal(c.nodes.get('taskCloudViewAreaRuns').disabled,false);hide.emit('click');assert.equal(changes.at(-1),true);
 c.cloud.areaChange({...area,hasSelection:false,total:0,boxVisible:false,successRate:null});assert.equal(hide.disabled,true);
});

test('native caption actions open the matching median and dismiss without changing camera, tints or points',()=>{
 const c=captionFixture(true),card=c.captionRoot.children.find(card=>!card.hidden),camera=c.canvas.dataset.cloudCamera;
 assert.equal(card.children[0].textContent,'Failure: 6/7');
 const view=card.children[3];assert.match(view.attributes['aria-label'],/View median failure run: Lift the bottle/);
 view.emit('click');c.draw();assert.equal(c.opened.at(-1).episode_id,'median_0');assert.equal(c.canvas.dataset.cloudCamera,camera);
 assert.equal(c.captionRoot.children.find(item=>!item.hidden),card,'draw reuses native buttons and keyboard focus');
 card.children[2].focus();card.children[2].emit('click');c.draw();
 assert.equal(card.hidden,true);assert.equal(c.doc.activeElement,c.canvas);assert.equal(c.canvas.dataset.renderedPoints,'7');assert.equal(c.canvas.dataset.highlightRegions,'1');assert.equal(c.canvas.dataset.cloudCamera,camera);
 c.cloud.setRuns(c.rows.map(run=>({...run})));c.cloud.setAreaLabels(true);c.draw();assert.equal(card.hidden,true,'unchanged refresh preserves dismissal');
 c.events.keydown({key:'ArrowRight',preventDefault(){}});c.draw();assert.equal(card.hidden,true);
 c.cloud.setAreaLabels(false);c.cloud.setAreaLabels(true);c.draw();assert.equal(card.hidden,false,'off/on restores dismissed captions');
});
test('native caption body retains preview and drag while hidden or filtered action buttons cannot open stale runs',()=>{
 const c=captionFixture(true),card=c.captionRoot.children.find(card=>!card.hidden),point=c.pointer(),camera=c.canvas.dataset.cloudCamera;
 card.emit('pointermove',point);assert.equal(c.previews.at(-1).run.episode_id,'median_0');
 card.emit('pointerdown',{...point,preventDefault(){}});c.events.pointermove({...point,clientX:point.clientX+40});c.events.pointerup(point);c.draw();
 assert.notEqual(c.canvas.dataset.cloudCamera,camera);assert.equal(c.opened.length,0);
 const view=card.children[3];c.cloud.setAreaLabels(false);view.emit('click');assert.equal(c.opened.length,0);
 c.cloud.setAreaLabels(true);c.draw();c.cloud.setRuns([]);view.emit('click');c.draw();assert.equal(c.opened.length,0);assert.equal(card.removed,true);
});

test('phone native captions leave room for both outcomes below in-cloud checkboxes',()=>{
 const c=setup(run=>run.testOutcome,true);c.canvas.clientWidth=354;c.canvas.clientHeight=360;
 c.captionRoot.parentElement={querySelector:()=>({getBoundingClientRect:()=>({left:8,top:8,bottom:106,width:338,height:98})})};
 const rows=['Success','Failure'].flatMap((testOutcome,index)=>Array.from({length:5},(_,i)=>({episode_id:`ep_${index}_${i}`,prompt:index?'Place blue block on the tray':'Place green block on the towel',xyz:index?[.07,0,.1]:[-.07,0,-.1],testOutcome})));
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();
 assert.deepEqual(c.captionRoot.children.filter(card=>!card.hidden).map(card=>card.dataset.outcome).sort(),['Failure','Success']);
});
test('count-only regions still have a dismissible label and View opens an actual median run',()=>{
 const c=setup(run=>run.testOutcome,true),rows=Array.from({length:5},(_,i)=>({episode_id:'blank'+i,prompt:'',xyz:[0,0,0],testOutcome:'Success'}));
 c.cloud.setRuns(rows);c.cloud.setHighlight('both');c.cloud.setAreaLabels(true);c.draw();
 const card=c.captionRoot.children[0];assert.equal(card.children[0].textContent,'Success: 5/5');card.children[3].emit('click');assert.equal(c.opened[0].episode_id,'blank0');
});

test('changing the frozen projection clears old geometry while same-map refresh keeps selection',()=>{
 const c=setup(), rows=[{episode_id:'a',prompt:'Apple',xyz:[0,0,0]}];
 c.cloud.setRuns(rows,null,'pca-map');c.cloud.addVolume();c.draw();
 assert.equal(c.areas.at(-1).hasSelection,true);
 c.cloud.setRuns(rows,null,'pca-map');c.draw();assert.equal(c.areas.at(-1).hasSelection,true);
 c.cloud.setRuns(rows,null,'umap-map');c.draw();
 assert.equal(c.areas.at(-1).hasSelection,false);assert.equal(c.canvas.dataset.volumeBox,'');
 assert.equal(c.canvas.dataset.mapVersion,'umap-map');assert.equal(c.canvas.dataset.renderedPoints,'1');
});
