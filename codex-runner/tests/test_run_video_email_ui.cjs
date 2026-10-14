const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const factory = vm.runInNewContext(source.split('function runComparisonBaseMetrics')[0] + '\ncreateRunVideoEmailControl');
function setup() {
  const nodes = new Map();
  const $ = id => {
    if (!nodes.has(id)) nodes.set(id, {value:'', checked:false, attributes:{'aria-pressed':'false'}, handlers:{},
      addEventListener(name, fn) { this.handlers[name] = fn; },
      getAttribute(name) { return this.attributes[name]; },
      setAttribute(name, value) { this.attributes[name] = value; },
      setCustomValidity(value) { this.error = value; },
      checkValidity() { return !this.error && this.value.includes('@'); },
      closest() { return this.dialog || null; },
      focus() { this.focused = true; }});
    return nodes.get(id);
  };
  return {$, control:factory($)};
}
test('opt-in requires an email and toggles back off without leaving a validation error', () => {
  const {$, control} = setup();
  assert.equal(control.enabled(), false);
  $('emailRunVideo').checked = !$('emailRunVideo').checked; $('emailRunVideo').handlers.change();
  assert.equal(control.enabled(), true);
  assert.equal(control.validate(), false);
  assert.equal($('email').focused, true);
  $('email').value = 'me@example.com'; $('email').handlers.input();
  assert.equal(control.validate(), true);
  $('emailRunVideo').checked = !$('emailRunVideo').checked; $('emailRunVideo').handlers.change();
  assert.equal(control.enabled(), false);
  assert.equal($('email').error, '');
});
test('submitting freezes the selection without dropping the request', () => {
  const {$, control} = setup();
  $('emailRunVideo').checked = !$('emailRunVideo').checked; $('emailRunVideo').handlers.change(); control.busy(true);
  assert.equal($('emailRunVideo').disabled, true);
  assert.equal(control.enabled(), true);
  control.busy(false);
  assert.equal($('emailRunVideo').disabled, false);
});

test('opting in reveals the hosted email dialog before focusing its required field', () => {
  const {$, control} = setup();
  const dialog = {open:false,showModal(){this.open=true;}};
  $('email').dialog = dialog;
  $('emailRunVideo').checked = !$('emailRunVideo').checked; $('emailRunVideo').handlers.change();
  assert.equal(dialog.open, true);
  assert.equal($('email').focused, true);
  $('email').value='me@example.com'; $('email').handlers.input();
  assert.equal(control.validate(), true);
});
