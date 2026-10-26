import * as THREE from './path-studio-three.js';
import { OrbitControls } from './path-studio-orbit.js';
import { STLLoader } from './path-studio-stl.js';
import { connectHardware } from './path-studio-api.js';

const C=window.PathStudioCore,$=id=>document.getElementById(id);
let hardware=null,editorLocked=false;
const viewport=$('viewport'),STORAGE='blupe.path-studio.bimanual.v1';
let renderer;
try { renderer=new THREE.WebGLRenderer({antialias:true,alpha:false}); }
catch { $('loading').textContent='This workspace needs WebGL. Enable hardware acceleration in your browser and refresh.';throw Error('WebGL unavailable'); }
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor('#101a14');
renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.outputColorSpace=THREE.SRGBColorSpace;viewport.append(renderer.domElement);$('loading').remove();
const scene=new THREE.Scene();scene.fog=new THREE.Fog('#101a14',2.4,5);
const camera=new THREE.PerspectiveCamera(39,1,.01,12);camera.up.set(0,0,1);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(.24,0,.24);controls.enableDamping=true;controls.minDistance=.4;controls.maxDistance=3;controls.maxPolarAngle=Math.PI*.49;controls.enabled=false;
scene.add(new THREE.HemisphereLight('#e1eed9','#273320',2.0));
const light=new THREE.DirectionalLight('#fcffe9',3.0);light.position.set(.4,-.7,1.7);light.castShadow=true;light.shadow.mapSize.set(2048,2048);light.shadow.camera.left=-1;light.shadow.camera.right=1;light.shadow.camera.top=1;light.shadow.camera.bottom=-1;light.shadow.normalBias=.008;scene.add(light);
const fill=new THREE.DirectionalLight('#b9d5cb',1);fill.position.set(-.8,.5,.7);scene.add(fill);
const frontLight=new THREE.DirectionalLight('#e3eaf0',2.5);frontLight.position.set(1.8,0,1);scene.add(frontLight);
const floor=new THREE.Mesh(new THREE.PlaneGeometry(6,6),new THREE.MeshStandardMaterial({color:'#142018',roughness:1}));floor.position.z=-.012;floor.receiveShadow=true;scene.add(floor);
const grid=new THREE.GridHelper(2,40,'#536142','#293c29');grid.rotation.x=Math.PI/2;grid.position.set(.25,0,-.01);grid.material.transparent=true;grid.material.opacity=.65;scene.add(grid);
const mat=(color,metalness=.2,roughness=.5)=>new THREE.MeshStandardMaterial({color,metalness,roughness});
function mesh(geometry,material,parent=scene) {const m=new THREE.Mesh(geometry,material);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
const COLORS={left:{path:'#c6f432',trace:'#75d5c7'},right:{path:'#efb36a',trace:'#f2a1b0'}};
const model=window.PathStudioYamModel,stlLoader=new STLLoader();
const modelGeometries=Object.fromEntries(Object.entries(model.meshes).map(([name,data])=>{
  const bytes=Uint8Array.from(atob(data),character=>character.charCodeAt(0));
  return [name,stlLoader.parse(bytes.buffer)];
}));
const bodyMaterial=mat('#4b5358',.48,.39),gripperMaterial=mat('#30383c',.4,.44);
function createArm(side) {
  const group=new THREE.Group();group.position.set(...C.BASES[side]);scene.add(group);
  const visuals=model.visuals.map(spec=>{
    const object=mesh(modelGeometries[spec.mesh],spec.mesh.startsWith('linear_')?gripperMaterial:bodyMaterial,group);object.matrixAutoUpdate=false;
    const origin=new THREE.Matrix4().set(...C.visualTransform(spec,0));
    return {object,origin,spec,index:spec.frame==='base_link'?-1:Number(spec.frame.replace('link',''))-1};
  });
  const tip=mesh(new THREE.SphereGeometry(.006,18,12),new THREE.MeshBasicMaterial({color:COLORS[side].trace}),group);
  return {group,visuals,tip,error:0};
}
const arms={left:createArm('left'),right:createArm('right')};
viewport.dataset.modelGeometry='controller-stl';viewport.dataset.modelMeshes=String(model.visuals.length*2);viewport.dataset.controllerCommit=model.provenance.controller_commit;
function pose(side,jointValues,target,gripper=0) {
  const arm=arms[side],fk=C.forward(jointValues);
  for(const visual of arm.visuals) {
    if(visual.spec.slide) {
      visual.object.visible=Number.isFinite(gripper)&&gripper>=0&&gripper<=1;
      if(visual.object.visible)visual.origin.set(...C.visualTransform(visual.spec,gripper));
    }
    const frame=visual.index<0?new THREE.Matrix4():new THREE.Matrix4().set(...fk.matrices[visual.index]);
    visual.object.matrix.copy(frame.multiply(visual.origin));
  }
  arm.tip.position.set(...fk.position);const actual=C.armWorld(fk.position,side);
  $(side+'Position').textContent=actual.map(v=>String(Math.round(v*1000))).join(' / ')+' mm';
  arm.error=target?C.distance(target,actual):0;
  $('trackingError').textContent=target?(Math.max(arms.left.error,arms.right.error)*1000).toFixed(2)+' mm':'—';
  return actual;
}
function sprite(text,color) {
  const canvas=document.createElement('canvas');canvas.width=128;canvas.height=64;const ctx=canvas.getContext('2d');ctx.font='500 28px monospace';ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(text,64,43);
  const texture=new THREE.CanvasTexture(canvas),s=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthTest:false}));s.scale.set(.07,.035,1);scene.add(s);return s;
}
for(const [direction,label,color] of [[[1,0,0],'X','#c9a68c'],[[0,1,0],'Y','#a9c385'],[[0,0,1],'Z','#8cb9c3']]) {
  const origin=new THREE.Vector3(-.13,-.28,.002),d=new THREE.Vector3(...direction);
  scene.add(new THREE.ArrowHelper(d,origin,.12,color,.015,.009));sprite(label,color).position.copy(origin).addScaledVector(d,.15);
}
const armLabels={left:sprite('LEFT',COLORS.left.path),right:sprite('RIGHT',COLORS.right.path)};
function stationGeometry() {
  const profile=C.setStation($('stationSelector').value);
  const spacing=hardware?.calibration()?.spacing_m;
  if(spacing){C.BASES.left[1]=spacing/2;C.BASES.right[1]=-spacing/2;}
  for(const side of ['left','right']) {arms[side].group.position.set(...C.BASES[side]);armLabels[side].position.set(0,C.BASES[side][1],.10);}
  $('stationGeometry').textContent=`${profile.name} · ${spacing?Math.round(spacing*1000)+' mm base spacing':'reading calibration…'}${hardware?.isReal()?' · API measurements':' · constrained simulation'}`;
  viewport.dataset.baseSpacingM=String(spacing||profile.spacing);
}
const planeMesh=new THREE.Mesh(new THREE.PlaneGeometry(.6,.6),new THREE.MeshBasicMaterial({color:'#a9d878',transparent:true,opacity:.055,side:THREE.DoubleSide,depthWrite:false}));scene.add(planeMesh);
const planeOutline=new THREE.LineSegments(new THREE.EdgesGeometry(planeMesh.geometry),new THREE.LineBasicMaterial({color:'#648746',transparent:true,opacity:.5}));scene.add(planeOutline);
const drawPlane=new THREE.Plane(),raycaster=new THREE.Raycaster();let planeName='xy',offset=.28,mode='draw';
function updatePlane(resetOffset=false) {
  planeName=$('plane').value;
  const config={xy:{label:'Height · Z',min:30,max:600,value:280},xz:{label:'Depth · Y',min:-600,max:600,value:0},yz:{label:'Reach · X',min:50,max:600,value:340}}[planeName];
  if(resetOffset) {$('planeOffset').min=config.min;$('planeOffset').max=config.max;$('planeOffset').value=config.value;}
  offset=Number($('planeOffset').value)/1000;$('offsetLabel').textContent=config.label;$('offsetValue').textContent=Math.round(offset*1000)+' mm';
  const normal=new THREE.Vector3(...({xy:[0,0,1],xz:[0,1,0],yz:[1,0,0]}[planeName]));drawPlane.set(normal,-offset);
  planeMesh.position.set(...({xy:[.31,0,offset],xz:[.31,offset,.32],yz:[offset,0,.32]}[planeName]));
  planeMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),normal);planeOutline.position.copy(planeMesh.position);planeOutline.quaternion.copy(planeMesh.quaternion);
  $('modeHint').querySelector('span').textContent=`Click or drag on ${planeName.toUpperCase()} · ${config.label.split(' · ')[1]} = ${Math.round(offset*1000)} mm`;
}
const pathGroup=new THREE.Group();scene.add(pathGroup);const traceGroup=new THREE.Group();scene.add(traceGroup);
let points=[],history=[],selected=-1,plan=null,planToken=0,playing=false,planning=false,travelled=0,lastFrame=0,badPoint=null,tracePoints={left:[],right:[]},promptRequest=0,replayTraceIndex=-1,replayTrace={left:null,right:null};
const presets={
  wave:()=>Array.from({length:25},(_,i)=>{const t=i/24;return [.34,-.22+.44*t,.30+.055*Math.sin(t*Math.PI*2)];}),
  arch:()=>Array.from({length:19},(_,i)=>{const t=i/18;return [.34,-.22+.44*t,.24+.15*Math.sin(t*Math.PI)];}),
  square:()=>C.fromPrompt('draw a square').points
};
function disposeGroup(group) {for(const child of [...group.children]) {child.geometry?.dispose();if(Array.isArray(child.material))child.material.forEach(m=>m.dispose());else child.material?.dispose();group.remove(child);}}
function lineIn(points,color,radius,parent,opacity=1) {
  for(let i=1;i<points.length;i++) {
    const a=new THREE.Vector3(...points[i-1]),b=new THREE.Vector3(...points[i]),d=b.clone().sub(a);if(d.length()<1e-7) continue;
    const m=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,d.length(),7),new THREE.MeshBasicMaterial({color,transparent:opacity<1,opacity}));
    m.position.copy(a).add(b).multiplyScalar(.5);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize());parent.add(m);
  }
}
function drawPath() {
  disposeGroup(pathGroup);const pointSides=new Map();
  try {for(const [side,path] of Object.entries(C.assignPath(points,$('armAssignment').value))){lineIn(path,COLORS[side].path,.0025,pathGroup);for(const p of path)pointSides.set(p,side);}}
  catch {lineIn(points,COLORS.left.path,.0025,pathGroup);}
  const stride=Math.max(1,Math.ceil(points.length/100));
  points.forEach((p,i)=>{if(i%stride&&i!==points.length-1&&i!==selected) return;
    const sphere=new THREE.Mesh(new THREE.SphereGeometry(i===selected?.008:points.length>40?.0035:.0055,12,8),new THREE.MeshBasicMaterial({color:i===selected?'#fffad1':COLORS[pointSides.get(p)||'left'].path}));sphere.position.set(...p);sphere.userData.index=i;pathGroup.add(sphere);
  });
  if(badPoint) {const m=mesh(new THREE.SphereGeometry(.012,18,12),new THREE.MeshBasicMaterial({color:'#ed936a'}),pathGroup);m.position.set(...badPoint);}
  const length=points.slice(1).reduce((s,p,i)=>s+C.distance(p,points[i]),0);$('pathLength').textContent=length?(length*1000).toFixed(0)+' mm':'—';$('pointCount').textContent=points.length;
}
function renderPoints() {
  const list=$('pointList');list.replaceChildren();
  if(!points.length) {const p=document.createElement('p');p.className='empty-points';p.textContent='Your path starts here. Draw in the workspace or add an XYZ point.';list.append(p);}
  // Large imported/freehand paths stay editable without thousands of DOM inputs.
  let start=0;if(selected>=100)start=Math.max(0,selected-45);
  const end=Math.min(points.length,start+100);
  if(points.length>100) {const p=document.createElement('p');p.className='field-hint';p.textContent=`Showing ${start+1}–${end} of ${points.length}. Select a point in the scene to edit it.`;list.append(p);}
  for(let i=start;i<end;i++) {
    const row=document.createElement('div');row.className='point-row';
    const label=document.createElement('button');label.className='point-id'+(selected===i?' active':'');label.textContent=String(i+1).padStart(2,'0');label.title='Select waypoint '+(i+1);label.onclick=()=>{selected=i;drawPath();renderPoints();};row.append(label);
    points[i].forEach((v,k)=>{const input=document.createElement('input');input.type='number';input.step='1';input.min=k===2?'20':'-800';input.max='800';input.value=String(Math.round(v*1000));input.setAttribute('aria-label',`Point ${i+1} ${'XYZ'[k]} in millimetres`);
      const commit=()=>{if(!input.checkValidity()||input.value===''||Number(input.value)/1000===points[i][k])return;remember();points[i][k]=Number(input.value)/1000;selected=i;changed({render:false});};input.oninput=commit;input.onchange=()=>{if(!input.checkValidity()||input.value===''){input.reportValidity();input.value=Math.round(points[i][k]*1000);return;}commit();};row.append(input);});
    const del=document.createElement('button');del.className='delete-point';del.textContent='×';del.setAttribute('aria-label',`Delete point ${i+1}`);del.onclick=()=>{remember();points.splice(i,1);selected=-1;changed();};row.append(del);list.append(row);
  }
  $('undo').disabled=!history.length;$('clear').disabled=!points.length;$('exportButton').disabled=points.length<2;
}
function remember() {history.push(points.map(p=>p.slice()));if(history.length>50)history.shift();}
function setMessage(text,error=false) {$('message').textContent=text;$('message').classList.toggle('error',error);$('statusDot').classList.toggle('error',error);}
function setStatus(title,detail) {$('playbackStatus').textContent=title;$('playbackDetail').textContent=detail;}
function transport() {if(hardware?.isReal()){hardware.renderControls();return;}$('playIcon').textContent=playing?'Ⅱ':'▶';$('playLabel').textContent=planning?'Verifying…':playing?'Pause':plan?'Play verified path':'Verify & play';$('play').disabled=planning||points.length<2;$('scrubber').disabled=!plan;}
function updateProgress() {
  if(hardware?.isReal())return;
  $('scrubber').value=plan?Math.round(travelled/plan.total*1000):0;
  $('timeLabel').textContent=`${travelled.toFixed(1)} / ${plan?plan.total.toFixed(1):'—'} s`;
}
function changed({render=true}={}) {
  planToken++;plan=null;planning=false;playing=false;travelled=0;badPoint=null;tracePoints={left:[],right:[]};disposeGroup(traceGroup);drawPath();if(render)renderPoints();
  $('simulationStatus').textContent='Ready to verify';$('simulationResult').textContent='The full motion must pass before playback.';$('saveVerification').disabled=true;
  viewport.dataset.simulationVerified='false';replayTraceIndex=-1;replayTrace={left:null,right:null};
  if(!hardware?.isReal()){for(const side of ['left','right'])pose(side,[-.024,.794,.645,-.375,-.021,-.012],null,1);}
  transport();updateProgress();setStatus(points.length>=2?'Ready to simulate':'Draw your path',points.length>=2?'Verify the full motion, then replay its joint packets.':'Place at least two points in the workspace.');
  if(hardware?.isReal()){setStatus('Path ready','Press Run on real arms to join the selected station queue.');setMessage('Real execution plans from measured joints, aligns the grippers, and checks the full path and swept CAD geometry.');}
  else setMessage('Simulation uses the real planner and read-only station calibration. No control session is created.');
  try {localStorage.setItem(STORAGE,JSON.stringify({schema:'blupe.bimanual-path.v1',units:'m',frame:'yam_common',station:C.getStation(),assignment:$('armAssignment').value,coordination:$('coordination').value,points}));}catch {setMessage('Browser storage is unavailable. Export JSON to save your path.');}
}
async function prepare() {
  const token=++planToken;planning=true;transport();
  $('simulationStatus').textContent='Verifying full motion…';$('saveVerification').disabled=true;
  setStatus('Checking real-arm constraints','Planning closure, alignment, approach, drawing and retreat…');
  try {
    const result=await hardware.simulate({station:$('stationSelector').value,assignment:$('armAssignment').value,
      frame:'yam_common',units:'m',speed_m_s:Number($('speed').value),coordination:$('coordination').value,points});
    if(token!==planToken)return false;
    if(!result.verification?.passed||!result.frames?.length)throw Error('The full simulation did not pass.');
    hardware.simulationGeometry(result.calibration);
    plan={...result,total:result.duration_s,paths:result.paths_m||C.assignPath(points,$('armAssignment').value)};
    travelled=0;moveTo(0,true);
    const v=result.verification;
    $('simulationStatus').textContent='Simulation passed';
    $('simulationResult').textContent=`${v.coordination==='together'?'Both arms together':'Take turns'} · ${v.waypoint_count} steps · ${v.min_gripper_clearance_m!=null?(v.min_gripper_clearance_m*1000).toFixed(1)+' mm minimum gripper gap · ':''}${(v.max_requested_path_deviation_m*1000).toFixed(2)} mm outline deviation`;
    $('saveVerification').disabled=false;viewport.dataset.simulationVerified='true';
    setMessage('Full motion verified. Actual tool strokes are shown; the desired outline stays visible underneath.');
    return true;
  } catch(error) {
    if(token===planToken){plan=null;$('simulationStatus').textContent='Simulation blocked';$('simulationResult').textContent=error.message;setStatus('Path needs an edit','Playback blocked by the real planner.');setMessage(error.message,true);}
    return false;
  } finally {if(token===planToken){planning=false;transport();updateProgress();}}
}
function replayJoints(frame,side) {
  return frame[side+'_joints_deg'].map((v,i)=>v*Math.PI/180+plan.calibration.joint_offsets_rad[side][i]);
}
function moveTo(seconds,resetTrace=false) {
  if(!plan)return;travelled=Math.max(0,Math.min(plan.total,seconds));
  const cursor=travelled*plan.cadence_hz,index=Math.min(plan.frames.length-1,Math.floor(cursor+1e-8));
  if(resetTrace||index<replayTraceIndex){disposeGroup(traceGroup);replayTraceIndex=-1;replayTrace={left:null,right:null};viewport.dataset.simulationTraceSegments='0';}
  // Consume every 10 Hz sample even when rendering skips a frame. Only draw
  // phases leave ink; alignment, approach, settling and retreat break strokes.
  for(let k=replayTraceIndex+1;k<=index;k++) {
    const frame=plan.frames[k];
    for(const side of ['left','right']) {
      const point=C.armWorld(C.forward(replayJoints(frame,side)).position,side);
      const trace=C.drawingTrace(replayTrace[side],point,plan.paths[side]||[],frame.phases[side]==='draw'?'sim:'+side:null,k/plan.cadence_hz);
      replayTrace[side]=trace.last;
      if(trace.segment){lineIn(trace.segment,COLORS[side].trace,.0031,traceGroup);viewport.dataset.simulationTraceSegments=String(Number(viewport.dataset.simulationTraceSegments||0)+1);}
    }
  }
  replayTraceIndex=index;
  const a=plan.frames[index],b=plan.frames[Math.min(index+1,plan.frames.length-1)],t=Math.min(1,cursor-index);
  for(const side of ['left','right']) {
    const qa=replayJoints(a,side),qb=replayJoints(b,side),g=a[side+'_gripper']+(b[side+'_gripper']-a[side+'_gripper'])*t;
    pose(side,qa.map((v,i)=>v+(qb[i]-v)*t),null,g);viewport.dataset[side+'Gripper']=String(g);
  }
  $('trackingError').textContent=(plan.verification.max_draw_error_m*1000).toFixed(3)+' mm';
  const motion=Object.entries(a.phases).find(([,phase])=>phase!=='settle');
  if(playing&&a.phases.left==='draw'&&a.phases.right==='draw')setStatus('Drawing with both arms','Synchronized motion · gripper clearance enforced');
  else if(playing&&motion)setStatus(({orient:'Aligning',approach:'Approaching with',draw:'Drawing with',retract:'Retracting'})[motion[1]]+' '+motion[0]+' arm','Verified simulation · same planner and limits as real execution');
  updateProgress();
}
async function togglePlayback() {
  if(hardware?.isReal()){await hardware.run();return;}
  if(playing){playing=false;setStatus('Paused','Edit the path, scrub, or press Play to continue.');transport();return;}
  if(!plan&&!(await prepare()))return;
  if(travelled>=plan.total)moveTo(0,true);
  playing=true;lastFrame=performance.now();setStatus('Playing verified motion','Starting with closed-gripper verification and tool alignment');transport();
}
$('play').onclick=togglePlayback;
$('reset').onclick=()=>{playing=false;if(plan)moveTo(0,true);else changed();setStatus('Ready to replay','Reference starting pose · fully open grippers');transport();};
$('scrubber').oninput=()=>{if(!plan)return;playing=false;moveTo(Number($('scrubber').value)/1000*plan.total,true);setStatus(travelled>=plan.total?'Simulation complete':'Inspecting verified motion',travelled>=plan.total?'Full drawing traced · real-arm constraints passed':'Press Play to continue from here.');transport();};
$('speed').onchange=()=>changed({render:false});
$('saveVerification').onclick=()=>{
  if(!plan)return;
  const receipt={schema:plan.schema,station:plan.station,calibration:plan.calibration,duration_s:plan.duration_s,verification:plan.verification};
  const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)+'\n'],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='blupe-simulation-verification.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
function setMode(value) {mode=value;controls.enabled=mode==='orbit';document.querySelector('.scene-panel').classList.toggle('orbit',mode==='orbit');
  for(const [id,active] of [['drawMode',mode==='draw'],['orbitMode',mode==='orbit']]) {$(id).classList.toggle('selected',active);$(id).setAttribute('aria-pressed',String(active));}
  planeMesh.visible=planeOutline.visible=mode==='draw';$('modeHint').firstChild.textContent='';
  $('modeHint').innerHTML=mode==='draw'?'<i></i>DRAW MODE<span></span>':'<i></i>ORBIT MODE<span>Drag to rotate · right-drag to pan · scroll to zoom</span>';if(mode==='draw')updatePlane();
}
$('drawMode').onclick=()=>setMode('draw');$('orbitMode').onclick=()=>setMode('orbit');$('plane').onchange=()=>updatePlane(true);$('planeOffset').oninput=()=>updatePlane();
$('armAssignment').onchange=()=>{hardware?.renderControls();changed();};
$('coordination').onchange=()=>changed();
$('stationSelector').onchange=()=>{hardware?.changedStation();stationGeometry();changed();};
function setView(name) {
  controls.target.set(.18,0,.25);
  camera.position.set(...({perspective:[1.35,-.9,.90],top:[.18,-.001,1.75],front:[1.85,0,.40]}[name]));camera.lookAt(controls.target);controls.update();
  document.querySelectorAll('[data-view]').forEach(button=>{button.classList.toggle('selected',button.dataset.view===name);button.setAttribute('aria-pressed',String(button.dataset.view===name));});
}
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>setView(button.dataset.view));$('resetView').onclick=()=>setView('perspective');
document.querySelectorAll('[data-preset]').forEach(button=>button.onclick=()=>{remember();points=presets[button.dataset.preset]();selected=-1;changed();});
async function drawPrompt() {
  const request=++promptRequest;
  try {
    const shape=C.fromPrompt($('shapePrompt').value);remember();points=shape.points;selected=-1;changed();
    $('plane').value='yz';updatePlane(true);setView('front');setMode('orbit');
    if(hardware?.isReal()){setStatus(`A ${shape.name} is ready`,'Press Run on real arms to queue this drawing.');return;}
    setStatus(`Drawing a ${shape.name}`,'Generating a path for the simulated arm…');
    await togglePlayback();
    if(playing&&request===promptRequest)setStatus(`Playing verified ${shape.name}`,'Full real-arm plan · simulation only');
  }catch(error){setMessage(error.message,true);}
}
$('shapeForm').onsubmit=event=>{event.preventDefault();drawPrompt();};
document.querySelectorAll('[data-prompt]').forEach(button=>button.onclick=()=>{$('shapePrompt').value=button.dataset.prompt;drawPrompt();});
$('undo').onclick=()=>{if(history.length){points=history.pop();selected=-1;changed();}};
$('clear').onclick=()=>{remember();points=[];selected=-1;changed();};
$('addPoint').onclick=()=>{if(points.length>=2000){setMessage('The preview supports at most 2,000 waypoints.',true);return;}remember();const p=points.length?points.at(-1).slice():[.3,0,.28];if(points.length)p[0]=Math.min(.8,p[0]+.025);points.push(p);selected=points.length-1;changed();$('pointList').scrollTop=$('pointList').scrollHeight;};
function ray(event) {const box=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((event.clientX-box.left)/box.width*2-1,-(event.clientY-box.top)/box.height*2+1),camera);}
function planePoint(event) {ray(event);const hit=new THREE.Vector3();if(!raycaster.ray.intersectPlane(drawPlane,hit))return null;const p=hit.toArray();if(p.some(v=>Math.abs(v)>.8)||p[2]<.02||p[2]>.8)return null;return p.map(v=>Math.round(v*1000)/1000);}
let gesture=null;
renderer.domElement.addEventListener('pointerdown',event=>{
  if(editorLocked||mode!=='draw'||event.button!==0)return;ray(event);
  const hit=raycaster.intersectObjects(pathGroup.children).find(h=>Number.isInteger(h.object.userData.index));
  if(!hit&&points.length>=2000){setMessage('The preview supports at most 2,000 waypoints.',true);return;}
  const p=planePoint(event);if(!p){setMessage('Choose a view facing the drawing plane, or draw closer to the arm.',true);return;}
  remember();gesture={id:event.pointerId,index:hit?hit.object.userData.index:null,start:[event.clientX,event.clientY],moved:false};renderer.domElement.setPointerCapture(event.pointerId);
  if(hit){selected=gesture.index;drawPath();renderPoints();}else{points.push(p);selected=points.length-1;changed();}
});
renderer.domElement.addEventListener('pointermove',event=>{
  if(editorLocked||!gesture||event.pointerId!==gesture.id)return;if(Math.hypot(event.clientX-gesture.start[0],event.clientY-gesture.start[1])<4&&!gesture.moved)return;
  const p=planePoint(event);if(!p)return;gesture.moved=true;
  if(gesture.index!==null){points[gesture.index]=p;selected=gesture.index;changed({render:false});}
  else if(points.length<2000&&C.distance(p,points.at(-1))>.012){points.push(p);selected=points.length-1;changed({render:false});}
});
function endGesture(event) {if(gesture?.id===event.pointerId){gesture=null;renderPoints();}}
renderer.domElement.addEventListener('pointerup',endGesture);renderer.domElement.addEventListener('pointercancel',endGesture);
viewport.addEventListener('keydown',event=>{if(event.target!==viewport&&event.target!==renderer.domElement)return;if(event.code==='Space'){event.preventDefault();if(!$('play').disabled)$('play').click();}if(event.key.toLowerCase()==='o')setMode('orbit');if(event.key.toLowerCase()==='d')setMode('draw');});
$('importButton').onclick=()=>$('fileInput').click();
$('fileInput').onchange=async event=>{const file=event.target.files[0];if(!file)return;try {if(file.size>512000)throw Error('Choose a JSON file smaller than 500 KB.');const data=JSON.parse(await file.text()),next=C.parsePath(data);C.samplePath(next);if(data.station&&!Object.hasOwn(C.STATIONS,data.station))throw Error('Unknown robot station in JSON.');remember();if(data.station){$('stationSelector').value=data.station;stationGeometry();}points=next;selected=-1;if(['together','sequential'].includes(data.coordination))$('coordination').value=data.coordination;if(['both','left','right'].includes(data.assignment))$('armAssignment').value=data.assignment;else if(data.frame==='yam_left_base')$('armAssignment').value='left';changed();setMessage(`Imported ${points.length} common-frame points from ${file.name}.`);}catch(error){setMessage('Import failed: '+error.message,true);}finally{event.target.value='';}};
$('exportButton').onclick=()=>{try{C.validatePoints(points);const value={schema:'blupe.bimanual-path.v1',units:'m',frame:'yam_common',robot:'yam',station:C.getStation(),assignment:$('armAssignment').value,bases_m:C.BASES,orientation:'level_forward_right_roll_90',coordination:$('coordination').value,speed_m_s:Number($('speed').value),points:points.map(p=>p.map(v=>Number(v.toFixed(6))))};const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='blupe-bimanual-path.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setMessage('Exported path in metres in the shared YAM frame, with arm assignment.');}catch(error){setMessage(error.message,true);}};
$('helpButton').onclick=()=>$('helpDialog').showModal();$('closeHelp').onclick=()=>$('helpDialog').close();
new ResizeObserver(()=>{const width=viewport.clientWidth,height=viewport.clientHeight;renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}).observe(viewport);
function animate(now) {
  requestAnimationFrame(animate);const dt=Math.min((now-lastFrame)/1000,.1);lastFrame=now;
  if(playing&&plan) {moveTo(travelled+dt);if(travelled>=plan.total){playing=false;setStatus('Simulation complete','Full drawing traced · real-arm constraints passed');transport();}}
  controls.update();renderer.render(scene,camera);
}
points=C.fromPrompt('draw a heart').points;let restored=false;
try {const saved=localStorage.getItem(STORAGE);if(saved){const parsed=JSON.parse(saved);if(parsed.points?.length>=2){points=C.parsePath(parsed);restored=true;}else if(Array.isArray(parsed.points)&&parsed.points.length===0){points=[];restored=true;}if(['together','sequential'].includes(parsed.coordination))$('coordination').value=parsed.coordination;if(['both','left','right'].includes(parsed.assignment))$('armAssignment').value=parsed.assignment;if(Object.hasOwn(C.STATIONS,parsed.station))$('stationSelector').value=parsed.station;}}catch{/* A corrupt or unavailable draft must not prevent opening the editor. */}
stationGeometry();$('plane').value='yz';updatePlane(true);setView('front');setMode('orbit');pose('left',C.HOME,null);pose('right',C.HOME,null);drawPath();renderPoints();transport();updateProgress();
if(restored)setStatus(points.length?'Restored your path':'Draw your path',points.length?'Saved locally in this browser. Press Play to preview.':'Place at least two points in the workspace.');
requestAnimationFrame(animate);
let measuredTrace={left:null,right:null};
hardware=connectHardware({C,getPoints:()=>points,geometry:stationGeometry,setStatus,setMessage,
  stopSimulation:()=>{playing=false;planToken++;planning=false;plan=null;transport();},
  clearTrace:()=>{tracePoints={left:[],right:[]};measuredTrace={left:null,right:null};disposeGroup(traceGroup);viewport.dataset.measuredTraceSegments='0';},
  editorLocked:value=>{editorLocked=value;},restoreEditor:()=>{renderPoints();},
  setModelVisible:value=>{for(const side of ['left','right']){arms[side].group.visible=value;if(!value)$(side+'Position').textContent='—';}},
  previewMode:()=>{stationGeometry();changed();transport();},
  measured:(observation,calibration,run,tracing)=>{
    let paths={};try{paths=run?.drawing?.paths_m||C.assignPath(points,$('armAssignment').value);}catch{/* Empty paths still show measured robot state. */}
    for(const side of ['left','right']) {
      const q=observation[side+'_joints_deg'];if(!Array.isArray(q)||q.length!==6||!q.every(Number.isFinite))continue;
      const grip=observation[side+'_gripper'],offsets=calibration.joint_offsets_rad[side],position=pose(side,q.map((v,i)=>v*Math.PI/180+offsets[i]),null,grip);
      viewport.dataset[side+'Gripper']=Number.isFinite(grip)?String(grip):'unknown';
      const stroke=tracing&&run?.drawing?.arms[side]==='draw'?run.session_id+':'+side:null;
      const result=C.drawingTrace(measuredTrace[side],position,paths[side]||[],stroke,observation.observed_at,run?.progress?.coordination==='together'?.03:.006);
      measuredTrace[side]=result.last;
      if(result.segment){lineIn(result.segment,COLORS[side].trace,.0031,traceGroup);viewport.dataset.measuredTraceSegments=String(Number(viewport.dataset.measuredTraceSegments||0)+1);}
    }
  }
});
hardware.start();
