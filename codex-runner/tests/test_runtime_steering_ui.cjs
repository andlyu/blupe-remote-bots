const {test} = require('node:test');
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
function fixture(send = async () => ({message:{state:'queued'}})) {
  const element = () => ({hidden:true,disabled:true,value:'',textContent:'',listeners:{},addEventListener(kind,fn){this.listeners[kind]=fn;}});
  const elements = Object.fromEntries(['form','input','button','feedback','delivery'].map(k=>[k,element()]));
  const c = vm.createContext({});
  vm.runInContext(source.slice(source.indexOf('function createSteeringComposer('),source.indexOf('function createRunLaunchGuard(')),c);
  let scope='robot-a:session-a', ids=0;
  const ui=c.createSteeringComposer({...elements,send,context:()=>scope,requestId:()=>`request_${++ids}`});
  return {...elements,ui,changeScope(){scope='robot-b:session-b';},type(text){elements.input.value=text;elements.input.listeners.input();},
    submit(){return elements.form.listeners.submit({preventDefault(){}});}};
}
const running = id => ({attempt_id:id,status:'running',steering:{supported:true,available:true,messages:[]}});
test('only owner status enables steering; polling preserves drafts',async()=>{
  const requests=[],f=fixture(async(path,payload)=>{requests.push({path,payload});return {message:{state:'queued'}};});
  f.ui.update({status:'idle',public_run:{status:'running',attempt_id:'someone-else'}});
  assert.equal(f.form.hidden,true);assert.equal(f.button.disabled,true);
  f.ui.update(running('mine'));f.type('Use the left arm');
  f.ui.update(running('mine'));assert.equal(f.input.value,'Use the left arm');
  await f.submit();assert.equal(requests[0].path,'/api/steer');assert.equal(requests[0].payload.attempt_id,'mine');
  assert.equal(f.input.value,'');assert.match(f.feedback.textContent,/queued/);
  f.ui.update({...running('mine'),steering:{supported:false,available:false,messages:[]}});
  assert.equal(f.input.disabled,true);assert.match(f.delivery.textContent,/unavailable/);
});
test('failed request preserves draft and reuses its ID on retry',async()=>{
  const requests=[],f=fixture(async(path,payload)=>{requests.push(payload);if(requests.length===1)throw Error('Network interrupted');return {message:{state:'included'}};});
  f.ui.update(running('mine'));f.type('Lift first');await f.submit();
  assert.equal(f.input.value,'Lift first');assert.match(f.feedback.textContent,/retry/);
  await f.submit();assert.equal(requests[0].request_id,requests[1].request_id);
  assert.match(f.feedback.textContent,/included/);
});
test('late responses cannot erase a new run or robot draft',async()=>{
  let resolve;const f=fixture(()=>new Promise(r=>resolve=r));
  f.ui.update(running('old'));f.type('old instruction');const pending=f.submit();
  assert.equal(f.button.disabled,true);
  f.changeScope();f.ui.update(running('new'));f.type('new instruction');
  resolve({message:{state:'queued'}});await pending;
  assert.equal(f.input.value,'new instruction');assert.equal(f.feedback.textContent,'');
  assert.equal(f.button.disabled,false);
});
test('terminal status disables submission and reports undelivered messages',async()=>{
  let calls=0;const f=fixture(async()=>{calls++;});f.ui.update(running('mine'));f.type('Lift');
  f.ui.update({...running('mine'),status:'stopped',steering:{supported:true,available:false,messages:[{state:'not_delivered'}]}});
  await f.submit();assert.equal(calls,0);assert.equal(f.input.disabled,true);assert.match(f.delivery.textContent,/ended before/);
});
