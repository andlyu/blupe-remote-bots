const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../static/hosted.js', 'utf8');

function fixture(send = async () => ({ok:true})) {
  const nodes = new Map(), calls = [], messages = [];
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {value:'kept draft', textContent:'', listeners:{},
      classList:{remove(){},add(){}}, addEventListener(kind, fn){this.listeners[kind]=fn;}});
    return nodes.get(id);
  };
  const state = {$, csrf:'session-token', ended:false, active:false, submitting:false,
    ownRunLive:false, conversationSharingAllowed:true,
    window:{}, runVideoEmail:{busy(){}}, updateRunLabel(){},
    runLaunchGuard:{resets:0,reset(){this.resets++;}},
    message:text=>messages.push(text), api:async (path,data)=>{calls.push({path,data});return send(path,data);}};
  vm.createContext(state);
  vm.runInContext(source.slice(source.indexOf('  function buttons() {'), source.indexOf('  let savedKeyProviders')), state);
  vm.runInContext(source.slice(source.indexOf("  $('resetRuns').addEventListener"), source.indexOf('  for (const [id, path, text] of [')), state);
  state.buttons();
  return {state,$,calls,messages,click:()=>$('resetRuns').listeners.click()};
}

test('only an explicit idle-session click resets allowance, preserving form drafts and session', async () => {
  let resolve;
  const f = fixture(() => new Promise(r=>resolve=r));
  assert.equal(f.calls.length,0);
  assert.equal(f.$('resetRuns').disabled,false);
  const pending = f.click();
  assert.equal(f.$('resetRuns').disabled,true);
  assert.equal(f.$('run').disabled,true);
  assert.equal(f.calls[0].path,'/api/runs/reset');
  await f.click(); assert.equal(f.calls.length,1);
  resolve({ok:true}); await pending;
  assert.match(f.$('resetRunsStatus').textContent,/Runs reset.*History and settings kept/);
  assert.equal(f.state.csrf,'session-token'); assert.equal(f.state.ended,false);
  for (const id of ['apiKey','prompt','runnerName','provider','model']) assert.equal(f.$(id).value,'kept draft');
  assert.equal(f.state.runLaunchGuard.resets,1);
  assert.equal(f.$('resetRuns').disabled,false);
  assert.equal(f.$('run').disabled,false);
  assert.equal(f.calls.length,1);
});

test('active, disconnected and submitting sessions cannot reset, including synthetic clicks', async () => {
  for (const state of [{active:true},{csrf:''},{ended:true},{submitting:true}]) {
    const f = fixture(); Object.assign(f.state,state); f.state.buttons();
    assert.equal(f.$('resetRuns').disabled,true);
    if (state.active) assert.match(f.$('resetRuns').title,/finish.*Stop/);
    await f.click(); assert.equal(f.calls.length,0);
  }
});

test('failed reset explains the problem, keeps drafts and permits retry without ending the session', async () => {
  const f = fixture(async () => {throw Error('Wait for your run to finish, or use Stop, before resetting runs.');});
  await f.click();
  assert.match(f.$('resetRunsStatus').textContent,/use Stop/);
  assert.equal(f.state.runLaunchGuard.resets,0);
  assert.equal(f.state.ended,false); assert.equal(f.$('prompt').value,'kept draft');
  assert.equal(f.$('resetRuns').disabled,false);
});
