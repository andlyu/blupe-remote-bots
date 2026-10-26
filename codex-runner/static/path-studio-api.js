import {observerView} from './path-studio-observer.js';
/* The browser holds a local CSRF token, never a BluPe session capability. */
export function connectHardware(hooks) {
  const $=id=>document.getElementById(id);
  let token=null,state=null,busy=false,polling=false,cameraAt=0,mode=$('connectionMode').value,locked=false,simulationCalibration=null;
  const observer=observerView(hooks.C);
  const active=()=>busy||Boolean(state?.run&&(state.run.stop_error||['preparing','queued','running'].includes(state.run.status)));
  const isReal=()=>mode==='real';
  const station=()=>$('stationSelector').value;
  const fresh=()=>state?.observation&&state.received_at&&Date.now()/1000-state.received_at<8&&Math.abs(Date.now()/1000-state.observation.observed_at)<10&&!state.error;
  async function request(path,body) {
    const response=await fetch('./api/path-studio/'+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json','X-Path-Studio-Token':token},body:JSON.stringify(body)});
    const result=await response.json();if(!response.ok)throw Error(result.error||'API request failed');return result;
  }
  async function configure() {
    if(token)return;
    const config=await request('config');token=config.csrf_token;
    $('queueName').value=config.identity.runner_name;$('queueEmail').value=config.identity.email;
    $('queueIdentitySummary').textContent=`Queue as ${config.identity.runner_name} · ${config.identity.email||'add your email below'}`;
  }
  function lockEditor(value) {
    if(value===locked)return;locked=value;
    document.querySelectorAll('.sidebar input,.sidebar select,.sidebar button:not(#expandObserver):not(#playObserver)').forEach(el=>{el.disabled=value;});
    $('stationSelector').disabled=$('connectionMode').disabled=value;
    $('speed').disabled=value;
    hooks.editorLocked(value);
    if(!value)hooks.restoreEditor();
  }
  function renderControls() {
    $('armAssignment').querySelector('option[value=both]').textContent='Both arms';
    $('coordinationControl').hidden=$('armAssignment').value!=='both';
    $('apiPanel').hidden=!isReal();$('stopReal').hidden=!isReal();$('reset').hidden=isReal();
    $('simulationPanel').hidden=isReal();
    observer.show(station());$('observerStation').textContent=$('stationSelector').selectedOptions[0].textContent+' · live station camera';
    $('sceneViewLabel').textContent=isReal()?'3D robot view':'Simulation';$('cameraDetails').hidden=!isReal();
    $('drawPrompt').textContent=isReal()?'Create path':'Verify & draw';$('footerMode').textContent=isReal()?'Robot API':'Verified simulation';
    $('promptHint').textContent=isReal()?'Selected grippers close before the arms approach your drawing.':'Uses the real planner, calibrated spacing and swept CAD checks.';
    if(!isReal())return;
    const running=active(),run=state?.run;
    lockEditor(running);
    $('playLabel').textContent=busy?'Sending…':running?'Run in progress':'Run on real arms';
    $('playIcon').textContent='▶';$('play').disabled=running||!token||!fresh()||!state?.calibration||hooks.getPoints().length<2;
    $('stopReal').disabled=!running||!token;$('scrubber').disabled=true;
    const progress=run?.progress,done=progress?.confirmed_samples||0,total=progress?.total_samples||0;
    $('scrubber').value=total?Math.round(done/total*1000):0;
    $('timeLabel').textContent=run?.run_elapsed_s!=null?`${run.run_elapsed_s.toFixed(1)} s`:'Not running';
  }
  function paint() {
    if(!isReal())return;
    const obs=state?.observation,run=state?.run,valid=fresh();
    const reason=obs?.safety?.reason?.replaceAll('_',' ');
    $('apiState').textContent=!obs?'Connecting to the robot…':!valid?'Station feedback unavailable':obs.mode==='DISABLED'?'Hardware disabled':`${obs.mode||'Connected'} · ${obs.settled?'settled':'moving'}`;
    $('apiDetail').textContent=state?.error||(!valid&&obs?'Measurements are stale. Waiting for fresh API feedback.':reason?`${reason}. Queued runs wait for station readiness.`:'Station measurements arrive through the Robot API.');
    $('apiQueue').textContent=`Queue · ${state?.queue?.waiting??'—'} waiting`;
    $('apiAge').textContent=obs?`Feedback · ${Math.max(0,Date.now()/1000-obs.observed_at).toFixed(1)} s ago`:'Feedback —';
    $('connectionBadge').textContent=valid?'API connected':'API reconnecting';
    $('connectionBadge').classList.toggle('unavailable',!valid);
    hooks.setModelVisible(Boolean(obs&&state?.calibration));
    if(obs&&state?.calibration)hooks.measured(obs,state.calibration,run,valid&&run?.status==='running');
    const gripText=a=>typeof obs?.[a+'_gripper']==='number'?obs[a+'_gripper']<=.05?'closed':`${Math.round(obs[a+'_gripper']*100)}% open`:'unknown';
    $('apiGrippers').textContent=`Grippers · left ${gripText('left')} / right ${gripText('right')}`;
    if(run) {
      const phase=run.progress?.phase;
      $('geometryStatus').textContent=run.progress?.preflight_validated?(run.progress.coordination==='together'?`Both arms together · ${(1000*run.progress.min_gripper_clearance_m).toFixed(1)} mm modeled gripper gap · ${(1000*run.progress.max_path_adjustment_m).toFixed(1)} mm adjustment`:'Full motion cleared by local CAD model'):run.status==='queued'?'Gripper plan · forward and level, right wrist 90°':'Checking modeled tool orientation and clearance';
      const complete=phase==='complete'&&['stopped','resetting'].includes(run.status)&&!run.error&&!run.stop_error;
      const labels={preparing:'Checking station calibration',queued:`Queued${run.queue_position?` · position ${run.queue_position}`:''}`,running:phase==='checking_entire_path'?'Checking the entire path':'Real arms following path',stopped:complete?'Drawing complete':run.error&&!run.progress?.confirmed_draw_samples?'Stopped before drawing':'Run stopped',failed:'Run failed',safety_aborted:'Stopped by station safety',timed_out:'Session timed out',disconnected:'API disconnected'};
      const motion=Object.entries(run.drawing?.arms||{}).find(([,p])=>p==='orient'||p==='approach'||p==='draw'||p==='retract');
      const bothDrawing=run.drawing?.arms?.left==='draw'&&run.drawing?.arms?.right==='draw';
      const phaseLabel=bothDrawing?'Drawing with both arms':motion?({orient:`Aligning ${motion[0]} gripper`,approach:`Approaching with ${motion[0]} arm`,draw:`Drawing with ${motion[0]} arm`,retract:`Retracting ${motion[0]} arm`})[motion[1]]:null;
      hooks.setStatus(complete?'Drawing complete':phase==='settling_pose'&&run.status==='running'?'Settling at the alignment target':phase==='closing_grippers'&&run.status==='running'?'Closing drawing grippers':run.status==='running'&&phaseLabel?phaseLabel:labels[run.status]||run.status,run.error||run.feedback_warning||run.stop_error||(complete?`Drawing confirmed · maximum endpoint error ${(1000*run.progress.max_tcp_error_m).toFixed(2)} mm`:run.status==='queued'?'Waiting for the API to grant this station.':`Confirmed samples · ${run.progress?.confirmed_samples||0} / ${run.progress?.total_samples||'—'}`));
      if(run.stop_error)hooks.setMessage(run.stop_error,true);
      else if(run.error)hooks.setMessage(run.error,true);
      else if(complete)hooks.setMessage('Drawing completed through the Robot API.');
    } else {$('geometryStatus').textContent='Gripper plan · forward and level, right wrist 90°';hooks.setStatus(valid?'Ready to queue a drawing':'Connecting to the station',valid?'Create a path, then press Run on real arms.':'Reading live feedback and calibration from the API.');}
    renderControls();
  }
  function cameraFrames() {
    if(!isReal()||Date.now()-cameraAt<2000)return;cameraAt=Date.now();
    for(const role of ['left','top','right']) {
      const container=$('camera'+role[0].toUpperCase()+role.slice(1)),caption=container.nextElementSibling.querySelector('span');
      let el=container.querySelector('img');if(!el){el=document.createElement('img');el.alt=`Live ${role} camera`;el.hidden=true;container.append(el);}
      el.onload=()=>{el.hidden=false;caption.textContent='live';};
      el.onerror=()=>{el.hidden=true;caption.textContent='unavailable';};
      el.src=`./api/path-studio/cameras/${role}.jpg?station=${encodeURIComponent(station())}&t=${cameraAt}`;
    }
  }
  async function poll() {
    if(!isReal()||polling)return;polling=true;const requested=station();
    try {
      await configure();
      const result=await request('status?station='+encodeURIComponent(requested));
      if(requested!==station())return;
      if(result.run&&['preparing','queued','running'].includes(result.run.status)&&result.run.station!==station()) {
        $('stationSelector').value=result.run.station;state=null;hooks.geometry();return;
      }
      state=result;if(state.run?.station!==station()&&!active())state.run=null;
      hooks.geometry();paint();cameraFrames();
    } catch(error) {
      if(requested===station()){$('apiState').textContent='Local API connection lost';hooks.setMessage(error.message,true);$('connectionBadge').textContent='API unavailable';$('play').disabled=true;}
    } finally {polling=false;}
  }
  async function run() {
    if(!isReal()||active())return;
    if(!$('queueName').checkValidity()||!$('queueEmail').checkValidity()){$('queueIdentityFields').open=true;$('queueName').reportValidity();$('queueEmail').reportValidity();return;}
    const identity={runner_name:$('queueName').value.trim(),email:$('queueEmail').value.trim()};
    $('queueIdentitySummary').textContent=`Queue as ${identity.runner_name} · ${identity.email}`;
    busy=true;renderControls();hooks.clearTrace();
    try {state=await request('run',{station:station(),assignment:$('armAssignment').value,coordination:$('coordination').value,frame:'yam_common',units:'m',speed_m_s:Number($('speed').value),points:hooks.getPoints(),identity});hooks.setMessage(`Queued as ${identity.runner_name}. Both arms follow the chosen coordination; geometry clearance is checked before motion.`);}
    catch(error){hooks.setMessage(error.message,true);}
    finally{busy=false;paint();}
  }
  $('stopReal').onclick=async()=>{
    $('stopReal').disabled=true;hooks.setStatus('Stopping your run','Waiting for the API acknowledgement…');
    try {const result=await request('stop',{});if(state)state.run=result.run;paint();}
    catch(error){hooks.setMessage(error.message,true);$('stopReal').disabled=false;}
  };
  function applyMode() {
    hooks.stopSimulation();hooks.clearTrace();lockEditor(false);hooks.geometry();
    if(isReal()){hooks.setModelVisible(false);hooks.setMessage('Grippers align forward and level; the right wrist rolls for clearance. The full path and sweeps are checked before motion.');poll();}
    else {hooks.setModelVisible(true);$('connectionBadge').textContent='Simulation';hooks.previewMode();}
    renderControls();
  }
  $('connectionMode').onchange=()=>{if(active())return;mode=$('connectionMode').value;applyMode();};
  setInterval(poll,500);
  return {isReal,run,renderControls,active,
    simulate:async sketch=>{await configure();return request('simulate',sketch);},
    simulationGeometry:calibration=>{simulationCalibration={station:station(),...calibration};hooks.geometry();},
    calibration:()=>!isReal()&&simulationCalibration?.station===station()?simulationCalibration:state?.station===station()?state.calibration:null,
    changedStation:()=>{state=null;simulationCalibration=null;cameraAt=0;hooks.clearTrace();hooks.setModelVisible(!isReal());poll();},start:applyMode};
}
