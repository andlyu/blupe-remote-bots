const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const helper = source.slice(source.indexOf('function createRunnerIdentity('), source.indexOf('function createRunVideoEmailControl('));

function fixture(storage = new Map()) {
  const nodes = {};
  const $ = id => nodes[id] ||= {value:'', open:false, required:false, handlers:{},
    get validity() { return {valid: (!this.required || !!this.value.trim()) &&
      (id !== 'email' || !this.value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.value))}; },
    addEventListener(type, fn) { this.handlers[type] = fn; },
    showModal() { this.open = true; }, focus() { this.focused = true; }};
  $('runnerName').required = true;
  const window = {yamShowModelOptions(open) { window.optionsOpen = open; }};
  const document = {createElement() { return {addEventListener(type, fn) { this[type] = fn; }}; }};
  const api = storage instanceof Map ? {getItem:key => storage.get(key), setItem:(key, value) => storage.set(key, value)} : storage;
  const control = vm.runInNewContext(helper + '\ncreateRunnerIdentity', {document, window})($, api);
  return {$, window, control, storage};
}

test('first entry is required; confirmation persists only trimmed name/email and survives reload', () => {
  const f = fixture();
  assert.equal(f.control.ready(), false);
  assert.equal(f.control.remember(), false);
  assert.equal(f.storage.size, 0);
  f.$('runnerName').value = ' Test Runner ';
  f.$('email').value = 'runner@example.invalid';
  assert.equal(f.control.ready(), false); // Typing is not confirmation.
  assert.equal(f.control.remember(), true);
  assert.deepEqual(JSON.parse(f.storage.get('yam-runner-identity-v1')), {name:'Test Runner', email:'runner@example.invalid'});
  const next = fixture(f.storage);
  assert.equal(next.control.ready(), true);
  assert.equal(next.$('runnerName').value, 'Test Runner');
  assert.equal(next.$('email').value, 'runner@example.invalid');
  assert.equal(next.$('chatName').value, 'Test Runner');
});

test('stored details never bypass current email requirements or invalid edits', () => {
  const f = fixture(); f.$('runnerName').value = 'Runner';
  assert.equal(f.control.remember(), true); // Standalone email is optional.
  f.$('email').required = true;
  assert.equal(f.control.ready(), false); // Hosted guest flow requires it.
  f.$('email').value = 'bad address';
  assert.equal(f.control.remember(), false);
  f.$('email').value = 'runner@example.invalid';
  assert.equal(f.control.remember(), true);
  f.$('runnerName').value = '  ';
  assert.equal(f.control.ready(), false);
});

test('malformed stored data keeps first-entry validation and empty defaults', () => {
  for (const raw of ['broken', 'null', '[]', '{"name":7,"email":"x@y.invalid"}',
    JSON.stringify({name:'x'.repeat(33), email:''}), JSON.stringify({name:'Runner', email:'bad address'})]) {
    const f = fixture(new Map([['yam-runner-identity-v1', raw]]));
    assert.equal(f.control.ready(), false, raw);
    assert.equal(f.$('runnerName').value, '', raw);
  }
});

test('blocked storage still reuses confirmed details for the current visit', () => {
  const f = fixture({getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); }});
  assert.equal(f.control.ready(), false);
  f.$('runnerName').value = 'Runner'; f.$('email').value = 'runner@example.invalid';
  assert.equal(f.control.remember(), true);
  assert.equal(f.control.ready(), true);
});

test('explicit editing opens the existing dialog without submitting and saves corrections', () => {
  const f = fixture(); f.$('runnerName').value = 'First'; f.control.remember();
  f.control.editButton.click();
  assert.equal(f.$('localRunDialog').open, true);
  assert.equal(f.$('runnerName').focused, true);
  assert.equal(f.window.optionsOpen, false);
  assert.equal(f.control.editButton.type, 'button');
  f.$('runnerName').value = 'Corrected'; f.$('email').value = 'corrected@example.invalid';
  f.control.remember();
  assert.equal(fixture(f.storage).$('runnerName').value, 'Corrected');
});

test('repeat Send uses native form validation; first entry and invalid options retain setup', () => {
  const start = source.indexOf('  function openRunIdentity()');
  const body = source.slice(start, source.indexOf("  send.addEventListener('click'", start));
  for (const remembered of [false, true]) {
    let submissions = 0, launches = 0;
    const f = fixture();
    f.$('runForm').requestSubmit = submitter => { assert.equal(submitter, f.$('run')); submissions++; };
    f.$('prompt').reportValidity = () => true;
    f.$('openLocalRun').click = () => { launches++; };
    const invalid = {willValidate:true,validity:{valid:false},parentElement:null,reportValidity(){this.reported=true;}};
    let fields = [];
    const context = vm.createContext({$:f.$, window:{yamRunnerIdentity:{ready:() => remembered}},
      options:{querySelectorAll:() => fields}, advanced:{contains:() => false}, showComposerOptions(){}});
    vm.runInContext(body, context);
    context.openRunIdentity();
    assert.equal(submissions, remembered ? 1 : 0);
    assert.equal(launches, remembered ? 0 : 1);
    assert.equal(f.$('localRunDialog').open, !remembered);
    fields = [invalid]; context.openRunIdentity();
    assert.equal(submissions, remembered ? 1 : 0);
    assert.equal(invalid.reported, true);
  }
});


test('hosted guest-entry delegation reuses identity without reopening the fallback dialog', () => {
  const f = fixture(); let submissions = 0;
  f.$('runForm').requestSubmit = submitter => { assert.equal(submitter, f.$('run')); submissions++; };
  const start = source.indexOf("  $('openLocalRun').onclick = () => {");
  const body = source.slice(start, source.indexOf("  $('closeLocalRun').onclick", start));
  const context = vm.createContext({$:f.$, window:{yamRunnerIdentity:{ready:()=>true}},
    active:false,submitting:false,ended:false,csrf:'fixture',updateRunLabel(){}});
  vm.runInContext(body, context); f.$('openLocalRun').onclick();
  assert.equal(submissions, 1);
  assert.equal(f.$('localRunDialog').open, false);
  context.active = true; f.$('openLocalRun').onclick();
  assert.equal(submissions, 1); // Existing in-progress-run guard remains authoritative.
});


test('the anonymous guest bypass is not saved as a confirmed person', () => {
  const f = fixture(); f.$('runnerName').value = 'Guest';
  assert.equal(f.control.remember(), false);
  assert.equal(f.control.ready(), false);
  assert.equal(f.storage.size, 0);
});
