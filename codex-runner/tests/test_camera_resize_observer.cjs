const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(process.env.YAM_TEST_HOSTED_JS || path.join(__dirname, '../static/hosted.js'), 'utf8');
const start = source.indexOf('  function fitCameras()');
const end = source.indexOf("  provider.addEventListener('change', updateComposer);", start);

function harness() {
  const frames = [], values = new Map(), writes = [];
  let onResize, onMutation;
  const viewer = {dataset: {layout: 'observer-focus'}};
  const queue = {offsetHeight: 44};
  const status = {offsetHeight: 20};
  const workspace = {clientWidth: 1404, clientHeight: 100,
    getBoundingClientRect: () => ({top: 68}),
    style: {
      setProperty: (name, value) => {writes.push(name); values.set(name, value);},
      removeProperty: name => {writes.push(name); values.delete(name);},
    },
  };
  Object.defineProperty(workspace.style, 'height', {
    get: () => values.get('height'),
    set: value => {writes.push('height'); values.set('height', value); workspace.clientHeight = parseFloat(value);},
  });
  const window = {innerWidth: 1440, innerHeight: 900, scrollY: 0,
    requestAnimationFrame: callback => {frames.push(callback); return frames.length;},
  };
  const context = {window, workspace, visuals: {clientWidth: 1037},
    $: id => id === 'liveViewer' ? viewer : id === 'yourQueue' ? queue : null,
    document: {querySelector: () => status},
    ResizeObserver: class {constructor(callback) {onResize = callback;} observe() {}},
    MutationObserver: class {constructor(callback) {onMutation = callback;} observe() {}},
  };
  vm.runInNewContext(source.slice(start, end), context);
  return {frames, values, writes, workspace, window,
    resize: () => onResize([]), mutation: () => onMutation([]),
    flush: () => frames.shift()(),
  };
}

test('camera observation never changes observed geometry during observer delivery', () => {
  const h = harness();
  h.resize();
  assert.deepEqual(h.writes, [], 'writing observed dimensions here causes a ResizeObserver loop error');
  assert.equal(h.workspace.clientHeight, 100);
  h.flush();
  assert.equal(h.workspace.clientHeight, 814);
});

test('a burst of resize and camera-layout notifications shares one animation frame', () => {
  const h = harness();
  h.resize(); h.resize(); h.mutation();
  assert.equal(h.frames.length, 1);
  h.flush();
  const height = h.values.get('height');
  h.resize(); h.resize();
  assert.equal(h.frames.length, 1);
  h.flush();
  assert.equal(h.values.get('height'), height, 'the follow-up layout converges');
  assert.equal(h.frames.length, 0);
});

test('a later resize reads fresh viewport dimensions in the queued frame', () => {
  const h = harness();
  h.resize();
  h.window.innerHeight = 700;
  h.flush();
  assert.equal(h.workspace.clientHeight, 614);
  h.window.innerWidth = 390;
  h.resize(); h.flush();
  assert.equal(h.values.has('height'), false);
  assert.equal(h.values.has('--console-camera-width'), false);
});
