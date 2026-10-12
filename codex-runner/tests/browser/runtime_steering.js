/* Full shared UI; every fetch is mocked. The fixture server rejects POSTs too. */
(() => {
  const requests = [], checks = [];
  const base = {status:'idle',interactions:{events:[]},saved_key_providers:[],
    queue_snapshot:{entries:[],stations:[]},whats_running:[],robot_auto_queue_enabled:true};
  const run = {attempt_id:'fixture-owner',run_id:'run_fixture',status:'running',
    runner_name:'Fixture owner',task:'Place the green block on the plate',model_name:'Astra',events:[]};
  let state = {...base, public_run:run}, polls = 0;
  window.fetch = async (input, options = {}) => {
    const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
    const payload = options.body ? JSON.parse(options.body) : {};
    requests.push({path,payload});
    let data;
    if (path === '/api/session') data = {csrf:'fixture',local_runner:true,default_provider:'codex',
      codex:{ready:true,message:'Fixture Codex'},cameras:[],model_cameras:[],video_stream:null,
      configured_providers:{},share_conversation:true,robot_id:'fixture',expires_in:3600};
    else if (path === '/api/robots') data={selected:'fixture',robots:[{id:'fixture',name:'Steering fixture',hardware:'yam',connected:true}]};
    else if (path === '/api/status') {data=state;polls++;}
    else if (path === '/api/models') data={source:'provider',models:[{id:'gpt-6-astra',label:'Astra'}]};
    else if (path === '/api/steer') {
      if (payload.attempt_id !== state.attempt_id) throw Error('Wrong run');
      const message={id:1,text:payload.text,state:'queued',request_id:payload.request_id};
      state.steering.messages=[message];
      state.public_run.events.push({id:1,kind:'steering_queued',message:payload.text,timestamp:Date.now()/1000});
      data={ok:true,message};
    } else if (path === '/api/chat') data={messages:[],visitor:'fixture'};
    else if (['/api/recordings','/api/past-runs','/api/run-comparisons'].includes(path)) data={runs:[],next_offset:null};
    else if (path === '/api/stream-health') data={ok:true};
    else throw Error('Unmocked request: '+path);
    return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
  };
  const $=id=>document.getElementById(id);
  const wait=async predicate=>{
    const start=performance.now();
    while(!predicate()) {
      if(performance.now()-start>8000) throw Error('Timed out waiting for UI');
      await new Promise(resolve=>setTimeout(resolve,30));
    }
  };
  const check=(condition,label)=>{checks.push({pass:!!condition,label});if(!condition)throw Error(label);};
  const owner=()=>({...base,status:'running',attempt_id:'fixture-owner',public_run:run,
    steering:{supported:true,available:true,messages:[]}});
  async function verify() {
    const report=document.createElement('pre');report.id='steeringReport';
    $('liveConversationPanel').append(report);
    try {
      await wait(()=>polls>0);
      check($('steeringForm').hidden,'Spectator cannot steer a public run');
      state=owner();await wait(()=>!$('steeringForm').hidden);
      $('steeringPrompt').value='Use the right arm instead; lift before moving sideways.';
      $('steeringPrompt').dispatchEvent(new Event('input',{bubbles:true}));
      $('steeringForm').requestSubmit();
      await wait(()=>requests.some(row=>row.path==='/api/steer'));
      const sent=requests.find(row=>row.path==='/api/steer').payload;
      check(sent.attempt_id==='fixture-owner' && sent.request_id.length>=16,'Submission binds attempt and retry identity');
      await wait(()=>$('steeringDelivery').textContent.includes('waiting'));
      check($('steeringPrompt').value==='','Accepted message clears the draft');
      check($('sideConversationMessages').textContent.includes(sent.text),'Owner message appears in decision notes');
      state.steering.messages[0].state='included';
      run.events.push({id:2,kind:'steering_included',message:'Steering included in model context',timestamp:Date.now()/1000});
      await wait(()=>$('steeringDelivery').textContent.includes('included'));
      $('steeringPrompt').value='Next correction';$('steeringPrompt').dispatchEvent(new Event('input'));
      const before=polls;await wait(()=>polls>=before+2);
      check($('steeringPrompt').value==='Next correction','Polling preserves an unsent correction');
      state={...state,status:'stopped',steering:{supported:true,available:false,messages:[{state:'not_delivered'}]}};
      await wait(()=>$('steeringDelivery').textContent.includes('ended before'));
      check($('steeringSend').disabled,'Ended runs reject UI submission');
      state={...owner(),steering:{supported:false,available:false,messages:[]}};
      await wait(()=>$('steeringDelivery').textContent.includes('unavailable'));
      check($('steeringPrompt').disabled,'Unsupported policy explains disabled steering');
      state={...base,public_run:run};await wait(()=>$('steeringForm').hidden);
      check($('steeringForm').hidden,'Returning to spectator hides the composer');
      state=owner();state.steering.messages=[{id:1,text:sent.text,state:'included'}];
      await wait(()=>!$('steeringForm').hidden && !$('steeringPrompt').disabled);
      report.dataset.result='pass';report.textContent='PASS · '+checks.length+' browser checks\n'+checks.map(x=>'✓ '+x.label).join('\n');
      $('steeringPrompt').scrollIntoView({block:'center'});
    } catch(error) {report.dataset.result='fail';report.textContent='FAIL · '+error.message+'\n'+JSON.stringify(checks,null,2);}
  }
  document.addEventListener('DOMContentLoaded',()=>setTimeout(verify,0));
})();
