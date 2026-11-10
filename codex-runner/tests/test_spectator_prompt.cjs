const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const context = vm.createContext({});
vm.runInContext(source.split('(() => {')[0], context);
const publicRun = {status:'running', task:'Move the red block.', attempt_id:'public-attempt', episode_id:'ep_public'};
const prompt = state => context.spectatorRunPrompt(state);

test('spectators and queued visitors see the active public prompt', () => {
  for (const status of ['idle', 'queued']) {
    assert.equal(prompt({status, attempt_id:'my-draft', public_run:publicRun}), publicRun.task);
  }
  assert.equal(prompt({status:'preparing', attempt_id:'another-attempt', public_run:publicRun}), publicRun.task);
});

test('the current runner does not get a spectator prompt', () => {
  assert.equal(prompt({status:'running', attempt_id:'public-attempt', public_run:publicRun}), '');
  assert.equal(prompt({status:'running', episode_id:'ep_public', public_run:{...publicRun, attempt_id:null}}), '');
  assert.equal(prompt({status:'preparing', public_run:publicRun}), '');
});

test('idle and completed public runs leave the spectator header empty', () => {
  assert.equal(prompt({status:'idle', public_run:null}), '');
  assert.equal(prompt({status:'idle', public_run:{...publicRun, status:'completed'}}), '');
});
