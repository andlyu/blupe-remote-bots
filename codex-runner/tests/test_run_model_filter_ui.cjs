const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const full = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const start = full.lastIndexOf('(() => {', full.indexOf('const zeroSecondVideo'));
const source = full.slice(start).split('\n})();')[0] + '\n})();';

function setup() {
  const nodes = new Map(), events = {}, requests = [];
  const element = () => ({children: [], listeners: {}, dataset: {}, style: {}, value: '', open: false,
    addEventListener(name, fn) {(this.listeners[name] ||= []).push(fn)},
    emit(name, event = {}) {for (const fn of this.listeners[name] || []) fn(event)},
    after() {}, append(...children) {this.children.push(...children)}, replaceChildren(...children) {this.children = children},
    removeAttribute() {}, setAttribute() {}, pause() {}, play() {return Promise.resolve()}, load() {},
    showModal() {this.open = true}, close() {this.open = false; this.emit('close')}, focus() {this.focused = true}
  });
  const document = {documentElement: {dataset: {}}, body: {dataset: {}}, addEventListener() {},
    getElementById(id) {if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id)}, createElement: element};
  vm.runInNewContext(source, {document, window: {addEventListener(name, fn) {events[name] = fn}},
    URLSearchParams, encodeURIComponent, renderStepMetricsChart() {}, renderRunMetrics() {},
    fetch(url, options) {return new Promise(resolve => requests.push({url, options, resolve}))}});
  const answer = (request, runs = [], next_offset = null, total = runs.length, stale = false, models) =>
    request.resolve({ok: true, json: async () => ({runs, next_offset, total, stale, models})});
  return {nodes, events, requests, answer, flush: () => new Promise(setImmediate)};
}
const run = {episode_id: 'ep_marker', episode_index: 1, robot_id: 'yam-1', prompt: 'Pick up a marker',
  camera_order: [], started_at: 1, video_url: 'https://example.com/marker.mp4', result: 'Failure',
  ending_reason: 'Marker slipped', result_reason: 'Marker slipped', search_match: {exact: [], related: [{query: 'pen', match: 'marker'}], partial: true}};

test('model choices filter all pages, preserve robot/refresh state, reject stale results and clear', async () => {
  const c = setup(); c.events['blupe-robot-selected']({detail: 'yam-1'});
  const model = c.nodes.get('pastRunsModel');
  const choose = value => {model.value = value; model.emit('change')};
  c.answer(c.requests[0], [], null, 0, false, ['Dream0', 'Dream0 Flash', '__unrecorded__']); await c.flush();
  assert.deepEqual(model.children.map(option => option.textContent), ['All models', 'Dream0', 'Dream0 Flash', 'Model not recorded']);
  choose('Dream0');
  assert.match(c.requests[1].url, /offset=0.*model=Dream0$/);
  c.answer(c.requests[1], [{...run, model:'Dream0'}], 12, 15, false, ['Dream0', 'Dream0 Flash']); await c.flush();
  assert.match(c.nodes.get('pastRunsStatus').textContent, /15 runs · newest first/);
  assert.match(c.nodes.get('pastRunsList').children[0].children[0].children[0].textContent, /Dream0/);
  c.nodes.get('morePastRuns').emit('click');
  assert.match(c.requests[2].url, /offset=12.*model=Dream0$/);
  c.events['blupe-robot-selected']({detail: 'so101'});
  assert.match(c.requests[3].url, /offset=0&robot_id=so101&model=Dream0$/);
  c.answer(c.requests[2], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsList').children.length, 0);
  c.answer(c.requests[3], [], null, 0, false, ['Other model']); await c.flush();
  assert.equal(model.value, 'Dream0');
  assert.match(c.nodes.get('pastRunsStatus').textContent, /No published runs for this model/);
  c.nodes.get('refreshPastRuns').emit('click');
  assert.match(c.requests[4].url, /offset=0.*model=Dream0$/);
  choose('Other & model');
  assert.match(c.requests[5].url, /model=Other%20%26%20model$/);
  choose('');
  assert.doesNotMatch(c.requests[6].url, /[?&]model=/);
  c.answer(c.requests[4], [run]); c.answer(c.requests[5], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsList').children.length, 0);
  c.answer(c.requests[6], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsStatus').textContent, '');
});
