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
  return {frames, values, writes, workspace, window, visuals:context.visuals,
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
  assert.equal(h.values.has('height'), false);
  assert.equal(h.values.get('--console-camera-width'), '1037px');
  assert.equal(h.values.get('--console-viewport-height'), '816px');
});

test('a burst of resize and camera-layout notifications shares one animation frame', () => {
  const h = harness();
  h.resize(); h.resize(); h.mutation();
  assert.equal(h.frames.length, 1);
  h.flush();
  const height = h.values.get('--console-camera-height');
  h.resize(); h.resize();
  assert.equal(h.frames.length, 1);
  h.flush();
  assert.equal(h.values.get('--console-camera-height'), height, 'the follow-up layout converges');
  assert.equal(h.frames.length, 0);
});

test('a later resize reads the new camera column width in the queued frame', () => {
  const h = harness();
  h.resize();
  h.window.innerHeight = 700;
  h.visuals.clientWidth = 900;
  h.flush();
  assert.equal(h.values.get('--console-camera-width'), '900px');
  assert.equal(h.values.get('--console-viewport-height'), '616px');
  h.window.innerWidth = 390;
  h.workspace.clientWidth = 354;
  h.visuals.clientWidth = 354;
  h.resize(); h.flush();
  assert.equal(h.values.has('height'), false);
  assert.equal(h.values.get('--console-camera-width'), '354px');
});

function wrappingFooterHarness(viewportHeight = 854) {
  const frames = [], values = new Map([['--console-camera-width', '1244px']]);
  let resize;
  const viewer = {dataset: {layout: 'observer-focus', detailLayout: 'side'}};
  const footer = {get offsetHeight() {
    return parseFloat(values.get('--console-camera-width')) < 1000 ? 273 : 199;
  }};
  const workspace = {clientWidth: 1680, clientHeight: 768,
    getBoundingClientRect: () => ({top: 68}),
    style: {setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key)},
  };
  Object.defineProperty(workspace.style, 'height', {set(value) {workspace.clientHeight = parseFloat(value);}});
  const window = {innerWidth: 1728, innerHeight: viewportHeight, scrollY: 0,
    requestAnimationFrame(callback) {frames.push(callback); return frames.length;},
  };
  vm.runInNewContext(source.slice(start, end), {window, workspace, visuals: {clientWidth: 1244},
    $: id => id === 'liveViewer' ? viewer : null,
    document: {querySelector: () => footer},
    ResizeObserver: class {constructor(callback) {resize = callback;} observe() {}},
    MutationObserver: class {observe() {}},
  });
  return {viewer, values, frame() {resize([]); frames.shift()();}};
}

test('a wrapping camera footer cannot alternate side and bottom thumbnails each frame', () => {
  const h = wrappingFooterHarness(), layouts = [];
  for (let i = 0; i < 8; i++) {
    h.frame();
    layouts.push(h.viewer.dataset.detailLayout + ':' + h.values.get('--console-camera-width') + ':' + h.values.get('--console-viewport-height'));
  }
  assert.equal(new Set(layouts).size, 1, 'camera width must converge instead of changing footer wrapping every frame');
  assert.equal(h.viewer.dataset.detailLayout, 'side');
});

test('side thumbnails stay inside the camera column without consuming the chat column', () => {
  const h = wrappingFooterHarness(2000);
  h.frame();
  assert.equal(h.viewer.dataset.detailLayout, 'side');
  assert.equal(h.values.get('--console-camera-width'), '1244px');
});
