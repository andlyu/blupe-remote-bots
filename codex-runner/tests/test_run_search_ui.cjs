const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const full = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const start = full.lastIndexOf('(() => {', full.indexOf('const zeroSecondVideo'));
const source = full.slice(start).split('\n})();')[0] + '\n})();';

function setup(initialSearch = '') {
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
  vm.runInNewContext(source, {document, window: {location: {search: initialSearch}, addEventListener(name, fn) {events[name] = fn}},
    URLSearchParams, encodeURIComponent, renderStepMetricsChart() {}, renderRunMetrics() {},
    fetch(url, options) {return new Promise(resolve => requests.push({url, options, resolve}))}});
  const answer = (request, runs = [], next_offset = null, total = runs.length, stale = false, models) =>
    request.resolve({ok: true, json: async () => ({runs, next_offset, total, stale, models})});
  const search = query => {nodes.get('pastRunsQuery').value = query; nodes.get('pastRunsSearch').emit('submit', {preventDefault() {}})};
  return {nodes, events, requests, answer, search, flush: () => new Promise(setImmediate)};
}
const run = {episode_id: 'ep_marker', episode_index: 1, robot_id: 'yam-1', prompt: 'Pick up a marker',
  camera_order: [], started_at: 1, video_url: 'https://example.com/marker.mp4', result: 'Failure',
  ending_reason: 'Marker slipped', result_reason: 'Marker slipped', search_match: {exact: [], related: [{query: 'pen', match: 'marker'}], partial: true}};

test('search replaces pending browse, explains partial matches, pages with query, and clears', async () => {
  const c = setup(); c.events['blupe-robot-selected']({detail: 'yam-1'});
  c.search(' put pens into a cup ');
  assert.match(c.requests[1].url, /offset=0&robot_id=yam-1&q=put%20pens%20into%20a%20cup/);
  c.answer(c.requests[0]); await c.flush();
  assert.equal(c.nodes.get('pastRunsStatus').textContent, 'Loading past runs…');
  c.answer(c.requests[1], [run], 12, 13); await c.flush();
  assert.match(c.nodes.get('pastRunsStatus').textContent, /13 matching videos/);
  const item = c.nodes.get('pastRunsList').children[0];
  assert.match(item.children[1].textContent, /Related: pen → marker · Partial task match/);
  item.children[0].emit('click');
  assert.equal(c.nodes.get('pastRunVideo').src, run.video_url);
  assert.match(c.nodes.get('pastRunDetails').textContent, /Failure: Marker slipped/);
  c.nodes.get('morePastRuns').emit('click');
  assert.match(c.requests[2].url, /offset=12.*q=put%20pens/);
  c.nodes.get('clearPastRunsSearch').emit('click');
  assert.doesNotMatch(c.requests[3].url, /[?&]q=/);
  assert.equal(c.nodes.get('pastRunsQuery').value, '');
  assert.equal(c.nodes.get('clearPastRunsSearch').hidden, true);
  c.answer(c.requests[2], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsList').children.length, 0);
  c.answer(c.requests[3]); await c.flush();
  assert.equal(c.nodes.get('pastRunsStatus').textContent, 'No published runs yet.');
});

test('new queries and robot switches ignore stale results; empty and error states are recoverable', async () => {
  const c = setup(); c.events['blupe-robot-selected']({detail: 'yam-1'});
  c.search('markers'); c.search('cups');
  c.answer(c.requests[1], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsList').children.length, 0);
  c.events['blupe-robot-selected']({detail: 'so101'});
  assert.match(c.requests[3].url, /robot_id=so101&q=cups/);
  c.answer(c.requests[2], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsList').children.length, 0);
  c.answer(c.requests[3], [], null, 0, true); await c.flush();
  assert.match(c.nodes.get('pastRunsStatus').textContent, /No matching videos.*saved results/);
  c.search('pen & cup');
  assert.match(c.requests[4].url, /q=pen%20%26%20cup/);
  c.requests[4].resolve({ok: false}); await c.flush();
  assert.match(c.nodes.get('pastRunsStatus').textContent, /temporarily unavailable/);
  c.nodes.get('refreshPastRuns').emit('click');
  assert.match(c.requests[5].url, /offset=0.*q=pen%20%26%20cup/);
  c.answer(c.requests[5]); await c.flush();
  assert.match(c.nodes.get('pastRunsStatus').textContent, /No matching videos/);
});

test('model choice filters all pages, survives search and robot changes, and can be cleared', async () => {
  const c = setup(); c.events['blupe-robot-selected']({detail: 'yam-1'});
  const model = c.nodes.get('pastRunsModel');
  const choose = value => {model.value = value; model.emit('change')};
  c.answer(c.requests[0], [], null, 0, false, ['Dream0', 'Dream0 Flash', '__unrecorded__']);
  await c.flush();
  assert.deepEqual(model.children.map(option => option.textContent),
    ['All models', 'Dream0', 'Dream0 Flash', 'Model not recorded']);
  choose('Dream0');
  assert.match(c.requests[1].url, /offset=0.*model=Dream0$/);
  c.answer(c.requests[1], [{...run, model:'Dream0'}], 12, 15, false, ['Dream0', 'Dream0 Flash']);
  await c.flush();
  assert.match(c.nodes.get('pastRunsStatus').textContent, /15 runs · newest first/);
  assert.match(c.nodes.get('pastRunsList').children[0].children[0].children[0].textContent, /Dream0/);
  c.nodes.get('morePastRuns').emit('click');
  assert.match(c.requests[2].url, /offset=12.*model=Dream0$/);
  c.search('pen');
  assert.match(c.requests[3].url, /offset=0.*model=Dream0&q=pen$/);
  c.nodes.get('clearPastRunsSearch').emit('click');
  assert.match(c.requests[4].url, /offset=0.*model=Dream0$/);
  assert.doesNotMatch(c.requests[4].url, /[?&]q=/);
  c.events['blupe-robot-selected']({detail: 'so101'});
  assert.match(c.requests[5].url, /robot_id=so101&model=Dream0$/);
  c.answer(c.requests[5], [], null, 0, false, ['Other model']); await c.flush();
  assert.equal(model.value, 'Dream0');
  assert.match(c.nodes.get('pastRunsStatus').textContent, /No published runs for this model/);
  choose('Other & model');
  assert.match(c.requests[6].url, /model=Other%20%26%20model$/);
  choose('');
  assert.doesNotMatch(c.requests[7].url, /[?&]model=/);
  c.answer(c.requests[6], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsList').children.length, 0);
  c.answer(c.requests[7], [run]); await c.flush();
  assert.equal(c.nodes.get('pastRunsStatus').textContent, '');
  c.nodes.get('refreshPastRuns').emit('click');
  assert.doesNotMatch(c.requests[8].url, /[?&]model=/);
});


test('shared apple link searches on initial catalog load and composes with model choice', async () => {
  const c = setup('?q=apple');
  assert.equal(c.nodes.get('pastRunsQuery').value, 'apple');
  assert.equal(c.nodes.get('clearPastRunsSearch').hidden, false);
  c.events['blupe-robot-selected']({detail: 'yam-1'});
  assert.match(c.requests[0].url, /q=apple/);
  c.answer(c.requests[0], [], null, 0, false, ['Dream0']); await c.flush();
  const model = c.nodes.get('pastRunsModel'); model.value = 'Dream0'; model.emit('change');
  assert.match(c.requests[1].url, /model=Dream0&q=apple/);
});
