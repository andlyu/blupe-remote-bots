const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('the shipped viewer loads a player that can fetch separate HLS audio renditions', () => {
  const staticDir = path.join(__dirname, '../static');
  const page = fs.readFileSync(path.join(staticDir, 'hosted.html'), 'utf8');
  const script = page.match(/src="\/static\/(hls[^"/]*\.js)"/);
  assert.ok(script, 'viewer must load an HLS player');
  const Hls = require(path.join(staticDir, script[1]));
  // The light build plays video-only when MediaMTX emits EXT-X-MEDIA audio.
  // Pinned upstream build contract: docs/refs/hls.js/README-1.7.2.md.
  assert.equal(typeof Hls.DefaultConfig.audioTrackController, 'function');
  assert.equal(typeof Hls.DefaultConfig.audioStreamController, 'function');
});
