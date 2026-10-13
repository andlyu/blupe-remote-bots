const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');
const renderer = source.match(/window.yamRecordingView = function[\s\S]*?\n};/)[0];

test('observer-first MP4s play directly without re-cropping', () => {
  const context = {window:{}, document:{createElement(){throw Error('Already composed');}}};
  vm.runInNewContext(renderer, context);
  assert.equal(context.window.yamRecordingView({}, ['observer','left','top','right'], 'observer-focus'), undefined);
});

test('legacy four-view exports retain their existing canvas arrangement', () => {
  const draws = [], events = {};
  const canvas = {setAttribute(){},getContext(){return {drawImage(...args){draws.push(args);}}}};
  const context = {window:{}, document:{createElement(){return canvas;},addEventListener(){}},
    IntersectionObserver:class {observe(){}}, cancelAnimationFrame(){}};
  vm.runInNewContext(renderer, context);
  const video = {readyState:2, videoWidth:1280, videoHeight:768, paused:true, after(){},
    classList:{add(){}},addEventListener(name, fn){events[name]=fn;}};
  const cleanup = context.window.yamRecordingView(video, ['top','observer','left','right']);
  assert.equal(typeof cleanup, 'function');
  events.loadeddata();
  assert.equal(draws.length, 4);
  assert.deepEqual(draws[0].slice(1), [640,60,640,324,0,0,960,486]);
  assert.deepEqual(draws[1].slice(1), [0,444,640,324,0,495,314,159]);
});

test('both modal and card pass the saved layout through', () => {
  assert.match(source, /yamRecordingView\?\.\(player, run.camera_order, run.video_layout\)/);
  assert.match(source, /yamRecordingView\?\.\(video, run.camera_order, run.video_layout\)/);
});
