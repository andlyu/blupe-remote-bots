const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const path = require('node:path');

{
  const file = path.join(__dirname, '../static/hosted.js');
  test('catalog card discovers available local replay', async () => {
    const js = fs.readFileSync(file, 'utf8');
    const code = js.slice(js.indexOf('  function renderBlocks('), js.indexOf('  const modelDisplayName'));
    const nodes = [];
    const element = tag => {
      const node = {tag, dataset: {}, style: {}, children: [], setAttribute() {}, addEventListener() {},
        append(...children) { this.children.push(...children); }};
      nodes.push(node);
      return node;
    };
    const list = element('ul'), calls = [];
    const sandbox = {AbortController, clearTimeout, setTimeout, encodeURIComponent,
      document: {createElement: element}, $: () => list, selectedRun: null, zeroSecondVideo: x => x === 0,
      previewViews: [], window: {}, labelSource: 'auto',
      fetch: async (url, opts) => {
        calls.push([url, opts.headers['X-Blupe-Robot']]);
        return {ok: true, json: async () => ({runs: [
          {episode_id: 'ep_recent', robot_id: 'other', video_url: '/wrong.mp4', video_duration_s: 2},
          {episode_id: 'ep_recent', robot_id: 'robot-ba8413962083809c', video_url: '/api/quick-replays/ep_recent/valid.mp4', video_duration_s: 2},
        ]})};
      }};
    const run = {episode_id: 'ep_recent', robot_id: 'robot-ba8413962083809c', prompt: 'Saved run'};
    vm.runInNewContext(code + '\nrenderBlocks([run]);', {...sandbox, run});
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(calls, [['/api/past-runs?episode_id=ep_recent&robot_id=robot-ba8413962083809c&preview=1', 'robot-ba8413962083809c']]);
    assert.equal(nodes.find(n => n.tag === 'video').src, '/api/quick-replays/ep_recent/valid.mp4');
    assert.equal(nodes.find(n => n.tag === 'video').hidden, false);
  });
}
