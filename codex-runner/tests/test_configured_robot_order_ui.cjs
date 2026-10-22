const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(__dirname + '/../static/hosted.js', 'utf8');
const initial = source.match(/^  let selectedRobot = .*;$/m)[0];
const load = source.slice(source.indexOf('  async function loadRobotSelector()'), source.indexOf('  async function start()', source.indexOf('  async function loadRobotSelector()')));
const refresh = source.slice(source.indexOf('  async function refreshRobotAvailability()'), source.indexOf('  setInterval(refreshRobotAvailability'));

async function browser({query = '', dedicated = null, allOffline = false} = {}) {
  const selector = {options: [], replaceChildren(...options) { this.options = options; },
    append(option) { this.options = this.options.filter(o => o !== option); this.options.push(option); }};
  const catalog = {default_order: true, selected: 'yam-1', robots: [
    {id: 'offline', name: 'Offline', hardware: 'makerarm', connected: false},
    {id: 'preferred', name: 'Preferred', connected: !allOffline},
    {id: 'yam-1', name: 'YAM', connected: !allOffline}]};
  const context = vm.createContext({window: {yamApplication: {defaultRobot: dedicated}, dispatchEvent() {}},
    location: {search: query}, URLSearchParams, CustomEvent: class {},
    $: () => selector, document: {createElement: () => ({})}, selectRobotPrompt() {},
    api: async () => structuredClone(catalog), updateCameraAvailability() {}});
  await vm.runInContext(initial + '\n' + load + '\n' + refresh + '\nloadRobotSelector()', context);
  return {catalog, context, selector, selected: () => vm.runInContext('selectedRobot', context)};
}

test('configured order stays exact, selects its first connected arm ahead of YAM', async () => {
  const state = await browser();
  assert.equal(state.selected(), 'preferred');
  assert.deepEqual(Array.from(state.selector.options, o => o.value), ['offline', 'preferred', 'yam-1']);
});

test('all-offline defaults to the first configured arm', async () => {
  assert.equal((await browser({allOffline: true})).selected(), 'offline');
});

test('explicit and dedicated selections override the configured default', async () => {
  assert.equal((await browser({query: '?robot_id=offline'})).selected(), 'offline');
  assert.equal((await browser({query: '?robot_id=preferred', dedicated: 'yam-1'})).selected(), 'yam-1');
});

test('saving a new order updates the selector without changing the active arm', async () => {
  const state = await browser();
  state.catalog.robots.reverse();
  await vm.runInContext('refreshRobotAvailability()', state.context);
  assert.deepEqual(Array.from(state.selector.options, o => o.value), ['yam-1', 'preferred', 'offline']);
  assert.equal(state.selected(), 'preferred');
  assert.equal(state.selector.value, 'preferred');
});
