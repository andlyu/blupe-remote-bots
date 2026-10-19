const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../static/replay-email.js'),'utf8');
function setup() {
  const nodes = new Map(), calls = [], timers = new Map(); let timerId = 0;
  for (const id of ['replayEmailButton','replayEmailHint','replayEmailStatus','replayEmailDialog','replayEmailForm',
    'replayEmailAddress','replayEmailSend','replayEmailError','replayEmailCancel','pastRunDialog']) {
    nodes.set(id,{value:'',hidden:false,disabled:false,open:false,textContent:'',events:{},
      addEventListener(name,fn){(this.events[name] ||= []).push(fn)},
      emit(name,event={preventDefault(){}}){return Promise.all((this.events[name]||[]).map(fn=>fn(event)))},
      showModal(){this.open=true},close(){this.open=false;this.emit('close')},focus(){},reportValidity(){return true}});
  }
  const context = vm.createContext({setTimeout(fn){timers.set(++timerId,fn);return timerId},clearTimeout(id){timers.delete(id)}});
  vm.runInContext(source,context);
  const control = context.createReplayEmailControl({$:id=>nodes.get(id),send:(url,body)=>new Promise((resolve,reject)=>calls.push({url,body,resolve,reject}))});
  control.configure({enabled:true},'session-1');
  const run = id => ({episode_id:id,robot_id:'robot-a',video_url:'https://public.example/replay.mp4',email:'original-owner@example.com'});
  const flush=()=>new Promise(setImmediate);
  return {nodes,calls,timers,control,run,flush,click:()=>nodes.get('replayEmailButton').emit('click'),submit:()=>nodes.get('replayEmailForm').emit('submit')};
}
test('opening a replay, typing and cancelling never enqueue; missing session email requires Send',async()=>{
  const c=setup();c.control.setRun(c.run('ep_a'));
  c.nodes.get('replayEmailAddress').value='typed@example.com';await c.nodes.get('replayEmailAddress').emit('input');
  assert.equal(c.calls.length,0);
  const click=c.click();c.calls[0].resolve({enabled:true,session_email:''});await click;
  assert.equal(c.nodes.get('replayEmailDialog').open,true);assert.equal(c.calls.length,1);
  await c.nodes.get('replayEmailCancel').emit('click');assert.equal(c.calls.length,1);
  const again=c.click();c.calls[1].resolve({enabled:true,session_email:''});await again;
  c.nodes.get('replayEmailAddress').value='self@example.com';const submitted=c.submit();
  assert.equal(c.calls[2].url,'/api/replay-email/request');
  assert.deepEqual(JSON.parse(JSON.stringify(c.calls[2].body)),{episode_id:'ep_a',consent:true,email:'self@example.com'});
  c.calls[2].resolve({request_id:'receipt',state:'queued'});await submitted;
  assert.equal(c.nodes.get('replayEmailDialog').open,false);
  assert.match(c.nodes.get('replayEmailStatus').textContent,/queued for self@example.com/);
});
test('one click uses the latest private run address and never the replay owner or typed form',async()=>{
  const c=setup();c.control.configure({enabled:true,session_email:'previous@example.com'},'session-1');c.control.setRun(c.run('ep_selected'));
  c.nodes.get('replayEmailAddress').value='typed@example.com';
  const first=c.click(),duplicate=c.click();assert.equal(c.calls.length,1);await duplicate;
  c.calls[0].resolve({enabled:true,session_email:'latest@example.com'});await c.flush();
  assert.equal(c.nodes.get('replayEmailDialog').open,false);
  assert.deepEqual(JSON.parse(JSON.stringify(c.calls[1].body)),{episode_id:'ep_selected',consent:true,use_session_email:true,session_email:'latest@example.com'});
  c.calls[1].resolve({request_id:'receipt',state:'queued'});await first;
  const poll=[...c.timers.values()][0]();c.calls[2].resolve({request_id:'receipt',state:'sent'});await poll;
  assert.match(c.nodes.get('replayEmailStatus').textContent,/Sent to latest@example.com/);
});
test('changing replay during context lookup or an open popup cannot send another replay',async()=>{
  const c=setup();c.control.setRun(c.run('ep_a'));const pending=c.click();c.control.setRun(c.run('ep_b'));
  c.calls[0].resolve({enabled:true,session_email:'self@example.com'});await pending;
  assert.equal(c.calls.length,1);
  const popup=c.click();c.calls[1].resolve({enabled:true,session_email:''});await popup;
  assert.equal(c.nodes.get('replayEmailDialog').open,true);
  c.control.setRun(c.run('ep_c'));c.nodes.get('replayEmailAddress').value='self@example.com';await c.submit();
  assert.equal(c.nodes.get('replayEmailDialog').open,false);assert.equal(c.calls.length,2);
});
test('new session clears remembered destination and late status; failures stay visible',async()=>{
  const c=setup();c.control.configure({enabled:true,session_email:'old@example.com'},'old');c.control.setRun(c.run('ep_a'));
  c.control.configure({enabled:true},'new');assert.equal(c.nodes.get('replayEmailHint').textContent,'');
  const click=c.click();c.calls[0].resolve({enabled:true,session_email:''});await click;
  c.nodes.get('replayEmailAddress').value='self@example.com';const attempt=c.submit();
  c.calls[1].reject(new Error('Please wait before requesting another video email'));await attempt;
  assert.match(c.nodes.get('replayEmailError').textContent,/Please wait/);
  assert.equal(c.nodes.get('replayEmailDialog').open,true);
});
test('published replay and initialized application capability are required for the action',async()=>{
  const c=setup();c.control.configure(undefined,'session-1');assert.equal(c.nodes.get('replayEmailButton').hidden,true);
  c.control.configure({enabled:true},'session-1');c.control.setRun({episode_id:'ep_pending',robot_id:'robot-a'});
  await c.click();assert.equal(c.calls.length,0);assert.equal(c.nodes.get('replayEmailButton').disabled,true);
});
