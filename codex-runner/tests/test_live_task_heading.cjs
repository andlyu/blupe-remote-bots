const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.slice(0, source.indexOf('function createProviderRunDuration')), context);
const heading = (run, result) => JSON.parse(JSON.stringify(context.currentRunHeading(run, result)));

test('the task remains identifiable through queue, running and terminal states', () => {
  const task = 'Pick up the apple';
  for (const [status, label] of [['queued','Queued'], ['preparing','Preparing'],
    ['running','Running'], ['stopped','Stopped'], ['completed','Completed'], ['failed','Failed']]) {
    assert.deepEqual(heading({task, status}), {task, status:label});
  }
  assert.equal(heading({task, status:'preparing', reviewing_prompt:true}).status, 'Reviewing prompt');
});

test('stopping or timing out never claims the task completed', () => {
  const run = {task:'Pick up the apple', status:'stopped'};
  assert.equal(heading(run).status, 'Stopped');
  assert.equal(heading({...run,error:'Run reached time limit'}).status, 'Time limit reached');
  assert.equal(heading({...run,error:'Camera unavailable'}).status, 'Failed');
  assert.equal(heading(run,{label:'Completed'}).status, 'Completed');
  assert.equal(heading(run,{label:'Could not complete'}).status, 'Could not complete');
});

test('clearing or switching robots removes the previous task without replacing it with a draft', () => {
  heading({task:'Pick up the apple', status:'running'});
  for (const run of [null, {}, {task:'   '}, {task:42}]) {
    assert.deepEqual(heading(run), {task:'',status:''});
  }
  assert.deepEqual(heading({task:'Place the cup',status:'queued'}), {task:'Place the cup',status:'Queued'});
});

test('task content stays literal and unknown states do not claim execution', () => {
  const task = '<img src=x onerror=alert(1)>\nPick up the apple';
  assert.equal(heading({task,status:'running'}).task, task);
  assert.equal(heading({task,status:'unrecognized'}).status, 'Status unavailable');
});

test('reported task progress supplies the heading when the top-level prompt is absent', () => {
  assert.deepEqual(heading({status:'running',task_progress:{task:'Pick up the apple'}}),
    {task:'Pick up the apple',status:'Running'});
});
