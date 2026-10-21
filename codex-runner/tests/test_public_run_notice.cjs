const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/hosted.js'),'utf8');
const helper = source.slice(source.indexOf('  function renderPublicRunNotice('), source.indexOf('  function render(state)'));
function fixture({chat=null,live=null}={}) {
  const element = {hidden:true, textContent:'', dataset:{}};
  const context = vm.createContext({$: id => id === 'aspireTaskPanel' ? chat : element,renderCurrentConversation:{lastRun:live}});
  vm.runInContext(helper,context);
  return {element, render:(state,failure) => context.renderPublicRunNotice(state,failure)};
}
test('time limit is a neutral stop for the runner, while a robot fault stays an error', () => {
  const {element,render}=fixture();
  const public_run={runner_name:'Tom',status:'timed_out',error:'Run reached time limit'};
  render({public_run});
  assert.equal(element.hidden,false);
  assert.equal(element.dataset.tone,'neutral');
  assert.equal(element.textContent,'Tom — Stopped: Run reached time limit');
  render({public_run,robot_fault:'Joint fault'});
  assert.equal(element.dataset.tone,'error');
  assert.equal(element.textContent,'Robot error: Joint fault');
});
test('recoverable warning stays visible without claiming a failed run', () => {
  const {element,render}=fixture();
  render({public_run:{runner_name:'Fixture',status:'running',warning:'Robot server connection interrupted; retrying.'}});
  assert.equal(element.hidden,false);
  assert.equal(element.dataset.tone,'warning');
  assert.match(element.textContent,/connection warning: Robot server/);
  assert.doesNotMatch(element.textContent,/run error/);
  render({public_run:{status:'running'}});
  assert.equal(element.hidden,true);
  assert.equal(element.textContent,'');
});
test('exhausted requests and terminal errors have distinct truthful messages', () => {
  const {element,render}=fixture();
  render({public_run:{status:'running',warning:'Robot server request failed; waiting for confirmed recovery.'}});
  assert.doesNotMatch(element.textContent,/retrying/);
  render({public_run:{status:'stopped',error:'Hardware feedback blocked',warning:'Old retry'}});
  assert.equal(element.dataset.tone,'error');
  assert.match(element.textContent,/run error: Hardware feedback blocked/);
  assert.doesNotMatch(element.textContent,/Old retry/);
});
test('terminal run cannot retain a recovery warning and robot faults stay errors', () => {
  const {element,render}=fixture();
  render({public_run:{status:'stopped',warning:'Old retry'}});
  assert.equal(element.hidden,true);
  render({robot_fault:'Joint fault'});
  assert.equal(element.dataset.tone,'error');
  assert.equal(element.textContent,'Robot error: Joint fault');
});
test('camera notice uses the same specific failure reason as task progress and Run', () => {
  const {element,render}=fixture();
  const reason='AspireNotReady: Reconciled ASPIRE feedback changed lease/cursor';
  render({public_run:{status:'stopped',error:'The run encountered a model or runner error.'}}, {reason});
  assert.equal(element.dataset.tone,'error');
  assert.match(element.textContent,/run error: AspireNotReady/);
  assert.doesNotMatch(element.textContent,/model or runner error/);
  assert.doesNotThrow(()=>render({}, {reason}),'rejected launches may not have a public run');
});

test('chat failures suppress their public duplicate while retaining unrelated errors and robot faults', () => {
  const failure={label:'Task failed',reason:'RuntimeError: exact failure',task:'Place the block.'};
  const chat={hidden:false,dataset:{enabled:'true',failureKey:JSON.stringify(failure)}};
  const {element,render}=fixture({chat,live:{attempt_id:'current'}});
  render({public_run:{attempt_id:'current',status:'stopped',error:'The run encountered a model or runner error.'}},failure);
  assert.equal(element.hidden,true);
  assert.equal(element.textContent,'');
  render({public_run:{attempt_id:'current',status:'stopped',error:failure.reason},robot_fault:'Joint fault'},failure);
  assert.equal(element.hidden,false);
  assert.equal(element.textContent,'Robot error: Joint fault');
  render({public_run:{attempt_id:'another',status:'stopped',error:'Unrelated failure'}},failure);
  assert.equal(element.hidden,false);
  assert.match(element.textContent,/Unrelated failure/);
});


test('render uses the tested notice helper and a specific public reason beats a generic task error', () => {
  assert.match(source,/renderPublicRunNotice\(state, taskFailure\)/);
  const {element,render}=fixture();
  render({public_run:{status:'failed',error:'Robot initialization was blocked by queue/API ownership.'}},
    {reason:'The run encountered a model or runner error.'});
  assert.match(element.textContent,/queue\/API ownership/);
  assert.doesNotMatch(element.textContent,/model or runner error/);
});


test('owner task view uses the public reason for the same attempt and ignores stale public errors', () => {
  const helpers=source.slice(source.indexOf('function aspireLiveTask('),source.indexOf('function aspireElapsed('));
  const context=vm.createContext({aspireSharedRun:run=>run});vm.runInContext(helpers,context);
  const run={attempt_id:'current',status:'failed',error:'Robot initialization was blocked by queue/API ownership.'};
  const state={attempt_id:'current',status:'failed',error:'RuntimeError: private payload'};
  const shown=context.taskRunFailure(context.aspireLiveTask(run,state));
  assert.equal(shown.reason,run.error);
  assert.doesNotMatch(shown.reason,/private/);
  const old={...run,attempt_id:'old'};
  assert.equal(context.aspireLiveTask(old,state).error,old.error);
});

test('legacy generic messages never replace a recorded cause or invent one', () => {
  const {element,render}=fixture();
  const generic='The run encountered a model or runner error.';
  render({public_run:{runner_name:'andrew',status:'stopped',error:generic}});
  assert.match(element.textContent,/without a recorded error detail/);
  assert.doesNotMatch(element.textContent,/model or runner error/);
  render({public_run:{runner_name:'andrew',status:'stopped',error:'RuntimeError: Dream preparation cancelled'}});
  assert.equal(element.textContent,'andrew — run error: RuntimeError: Dream preparation cancelled');
  const helpers=source.slice(source.indexOf('function aspireLiveTask('),source.indexOf('function aspireElapsed('));
  const context=vm.createContext({aspireSharedRun:run=>run});vm.runInContext(helpers,context);
  assert.doesNotMatch(context.taskRunFailure({status:'stopped',error:generic}).reason,/model or runner error/);
});
