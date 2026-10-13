const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../static/hosted.js', 'utf8');
const body = source.slice(source.indexOf('function bindQuickTaskDraft('), source.indexOf('// Compact controls delegate'));
class Field extends EventTarget {
  constructor(value = '') { super(); this.raw = value; }
  get value() { return this.raw; }
  set value(value) { this.raw = String(value); }
  type(value) { this.raw = value; this.dispatchEvent(new Event('input')); }
}
function setup() {
  const prompt = new Field('Initial task'), quick = new Field();
  vm.runInNewContext(body + '\nbindQuickTaskDraft(prompt, quick);', {prompt, quick, Event});
  return {prompt, quick};
}
test('typing in either entry updates the shared draft and notifies full composer listeners', () => {
  const {prompt, quick} = setup(); let events = 0;
  prompt.addEventListener('input', () => events++);
  assert.equal(quick.value, 'Initial task');
  quick.type('Stack the blocks'); assert.equal(prompt.value, 'Stack the blocks'); assert.equal(events, 1);
  prompt.type('Move the red block'); assert.equal(quick.value, 'Move the red block'); assert.equal(events, 2);
});
test('programmatic defaults and assignments synchronize without erasing a multiline full prompt', () => {
  const {prompt, quick} = setup();
  prompt.value = 'First line\nSecond line';
  assert.equal(quick.value, 'First line Second line'); assert.equal(prompt.value, 'First line\nSecond line');
  prompt.value = 'Raise and lower both arms.'; assert.equal(quick.value, prompt.value);
  quick.value = 'New task'; assert.equal(prompt.value, 'New task');
  prompt.value = ''; assert.equal(quick.value, '');
});
