const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.split('(() => {')[0], context);

test('preparing and running public runs supply the banner prompt', () => {
  for (const status of ['preparing', 'running']) {
    assert.equal(context.activeRunPrompt({status, task:'Move the red block.'}), 'Move the red block.');
  }
  assert.equal(context.activeRunPrompt({status:'running', task_progress:{task:'Raise the cup.'}}), 'Raise the cup.');
});

test('inactive runs and active runs without a prompt leave the banner empty', () => {
  for (const status of ['queued', 'idle', 'completed', 'stopped']) {
    assert.equal(context.activeRunPrompt({status, task:'Move the red block.'}), '');
  }
  assert.equal(context.activeRunPrompt(null), '');
  assert.equal(context.activeRunPrompt({status:'running'}), '');
});
