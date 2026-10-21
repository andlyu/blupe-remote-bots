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
    } else if (path === '/api/stop') {
      state={...state,status:'stopped',steering:{supported:true,available:false,messages:[]}};
      data={ok:true};
    } else if (path === '/api/chat') data={messages:[],visitor:'fixture'};
    else if (['/api/recordings','/api/past-runs','/api/my-runs','/api/run-comparisons'].includes(path)) data={runs:[],next_offset:null};
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
  const preview=new URLSearchParams(location.search).get('preview');
  if(preview && preview!=='idle') state=owner();
  async function verify() {
    const report=document.createElement('pre');report.id='steeringReport';
    $('liveConversationPanel').append(report);
    try {
      await wait(()=>polls>0);
      $('prompt').value='Original task draft';
      check($('steeringHelp').hidden && !window.yamRuntimeSteering.available,'Spectator cannot steer a public run');
      check(!$('prompt').disabled,'Spectator retains the next-task composer');
      check($('quickTaskEntry').getBoundingClientRect().height>=44,'Idle camera shortcut stays readable in a small camera grid');
      check(!$('steeringForm') && !$('steeringPrompt'),'No separate intervention input');
      state=owner();await wait(()=>!$('steeringHelp').hidden && !$('prompt').disabled);
      check($('prompt').value==='' && $('prompt').maxLength===2000,'Main composer switches to an empty prompt update');
      check($('quickTaskEntry').getClientRects().length===0,'Running intervention has no duplicate camera entry');
      check($('composerSend').getAttribute('aria-label')==='Update prompt','Main send button clearly updates the running task');
      check(!$('composerStop').disabled && $('composerStop').getClientRects().length>0,'Separate Stop is visible beside the main send control');
      $('prompt').value='Use the right arm instead; lift before moving sideways.';
      $('prompt').dispatchEvent(new Event('input',{bubbles:true}));
      await wait(()=>!$('composerSend').disabled);$('composerSend').click();
      await wait(()=>requests.some(row=>row.path==='/api/steer'));
      const sent=requests.find(row=>row.path==='/api/steer').payload;
      check(sent.attempt_id==='fixture-owner' && sent.request_id.length>=16,'Submission binds attempt and retry identity');
      await wait(()=>$('steeringDelivery').textContent.includes('waiting'));
      check($('prompt').value==='','Accepted message clears the draft');
      check($('sideConversationMessages').textContent.includes(sent.text),'Owner message appears in decision notes');
      state.steering.messages[0].state='included';
      run.events.push({id:2,kind:'steering_included',message:'Steering included in model context',timestamp:Date.now()/1000});
      await wait(()=>$('steeringDelivery').textContent.includes('included'));
      $('prompt').value='Next correction';$('prompt').dispatchEvent(new Event('input'));
      const before=polls;await wait(()=>polls>=before+2);
      check($('prompt').value==='Next correction','Polling preserves an unsent correction');
      state={...state,status:'stopped',steering:{supported:true,available:false,messages:[{state:'not_delivered'}]}};
      await wait(()=>$('steeringDelivery').textContent.includes('ended before'));
      check(!window.yamRuntimeSteering.available && $('prompt').value==='Original task draft','Ended runs restore the task draft and leave intervention mode');
      state={...owner(),steering:{supported:false,available:false,messages:[]}};
      await wait(()=>$('steeringDelivery').textContent.includes('unavailable'));
      check($('prompt').disabled,'Unsupported policy explains disabled steering');
      check($('quickTaskEntry').getClientRects().length>0,'Unsupported runs retain the existing camera stop shortcut');
      state={...base,public_run:run};await wait(()=>$('steeringHelp').hidden && !$('prompt').disabled);
      check($('steeringHelp').hidden,'Returning to spectator hides intervention guidance');
      $('chatName').value='Fixture visitor';$('chatText').value='Hello from a spectator';
      $('chatForm').requestSubmit();await wait(()=>requests.some(row=>row.path==='/api/chat' && row.payload.text));
      check(requests.filter(row=>row.path==='/api/steer').length===1,'Social messages stay on the ordinary chat endpoint');
      state=owner();state.steering.messages=[{id:1,text:sent.text,state:'included'}];
      await wait(()=>!$('steeringHelp').hidden && !$('prompt').disabled);
      $('prompt').value='Keep the block upright';$('prompt').dispatchEvent(new Event('input',{bubbles:true}));
      await wait(()=>!$('composerSend').disabled);
      $('prompt').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
      await wait(()=>requests.filter(row=>row.path==='/api/steer').length===2);
      check(!requests.some(row=>['/api/run','/api/stop'].includes(row.path)),'Prompt submission neither restarts nor stops the run');
      $('composerStop').click();await wait(()=>requests.some(row=>row.path==='/api/stop'));
      check(requests.filter(row=>row.path==='/api/stop').length===1,'Separate Stop delegates to the existing stop pathway');
      state=owner();await wait(()=>!$('steeringHelp').hidden && !$('prompt').disabled);
      report.dataset.result='pass';report.textContent='PASS · '+checks.length+' browser checks\n'+checks.map(x=>'✓ '+x.label).join('\n');
      $('prompt').scrollIntoView({block:'center'});
    } catch(error) {report.dataset.result='fail';report.textContent='FAIL · '+error.message+'\n'+JSON.stringify(checks,null,2);}
  }
  if(!preview) document.addEventListener('DOMContentLoaded',()=>setTimeout(verify,0));
})();
