const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

// Also run against the exact hosted compatibility bundle before deployment:
// HOSTED_JS_UNDER_TEST=/path/to/hosted.js node --test this-file.cjs
const source = fs.readFileSync(process.env.HOSTED_JS_UNDER_TEST || path.join(__dirname, '../static/hosted.js'), 'utf8');
const recorded = require('./fixtures/dream-rejected-owner-state.json');
function fixture() {
  const nodes = {};
  const c = vm.createContext({$:id=>nodes[id] ||= {hidden:true,dataset:{},textContent:''},
    sharedTaskRun:r=>r,aspireSharedRun:r=>r,renderCurrentConversation:{lastRun:recorded.public_run}});
  function load(name) {
    const start = source.indexOf('function '+name+'(');
    assert.ok(start >= 0, name+' must exist');
    const indent = source.slice(source.lastIndexOf('\n',start)+1,start);
    const end = source.indexOf('\n'+indent+'}',start)+indent.length+2;
    vm.runInContext(source.slice(start,end),c);
  }
  const project = source.includes('function aspireLiveTask(') ? 'aspireLiveTask' : 'currentTaskRun';
  for (const name of ['createRunLaunchGuard',project,'taskRunFailure','renderPublicRunNotice','modelResponseTools','modelRunResult','renderModelRunResult']) load(name);
  if(source.includes('function publicRunErrorForAttempt(')) load('publicRunErrorForAttempt');
  return {c,nodes,project};
}

test('recorded Dream1 rejection survives owner projection, failure banner and outcome rendering', () => {
  const {c,nodes,project} = fixture();
  const run = recorded.public_run, state = {...recorded.owner_status, public_run:run};
  const guard = c.createRunLaunchGuard();
  const version = guard.start({task:run.task,runner_name:run.runner_name});
  guard.accept(version,run.attempt_id);
  const live = guard.conversation(run,state);
  const projected = c[project](live,state);
  assert.equal(projected.error,run.error);
  const failure = c.taskRunFailure(projected);
  assert.equal(failure,null);
  c.renderPublicRunNotice(state,failure);
  assert.equal(nodes.publicRunError.dataset.tone,'warning');
  assert.equal(nodes.publicRunError.textContent,'Andrew — Dream1 rejected this prompt.');
  assert.doesNotMatch(nodes.publicRunError.textContent,/run error|controller_executor_failed/);
  c.renderModelRunResult(projected);
  assert.equal(nodes.runOutcomeTitle.textContent,'Dream1 rejected this prompt');
  assert.equal(nodes.runOutcomeSummary.textContent,'Do a backflip');
  assert.equal(nodes.runOutcomeSummary.hidden,false);
});

test('a previous attempt cannot hide the current error and robot faults keep priority', () => {
  const {c,nodes,project} = fixture();
  const run = {...recorded.public_run,attempt_id:'current',error:'Current camera failure'};
  const state = {...recorded.owner_status,attempt_id:'current',public_run:run};
  assert.equal(c[project](run,state).error,run.error);
  const newer = {...run,attempt_id:'newer'};
  assert.notEqual(c[project](newer,state).error,recorded.public_run.error);
  c.renderPublicRunNotice({...state,public_run:recorded.public_run,robot_fault:'Joint fault'});
  assert.equal(nodes.publicRunError.dataset.tone,'error');
  assert.equal(nodes.publicRunError.textContent,'Robot error: Joint fault');
});
