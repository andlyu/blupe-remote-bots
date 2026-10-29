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
  const draws = [], events = {}; let intersection;
  const canvas = {setAttribute(){},getContext(){return {drawImage(...args){draws.push(args);}}}};
  const context = {window:{}, document:{createElement(){return canvas;},addEventListener(){}},
    IntersectionObserver:class {constructor(callback){intersection=callback} observe(){}}, cancelAnimationFrame(){}};
  vm.runInNewContext(renderer, context);
  let pauses = 0;
  const video = {readyState:2, videoWidth:1280, videoHeight:768, paused:true, after(){},pause(){pauses++},
    classList:{add(){}},addEventListener(name, fn){events[name]=fn;}};
  const cleanup = context.window.yamRecordingView(video, ['top','observer','left','right']);
  assert.equal(typeof cleanup, 'function');
  intersection([{isIntersecting:false}]);assert.equal(pauses,0,'Hidden initial composite must not abort lazy play');
  events.loadeddata();
  intersection([{isIntersecting:false}]);assert.equal(pauses,1,'Decoded offscreen composites still pause');
  assert.equal(draws.length, 4);
  assert.deepEqual(draws[0].slice(1), [640,60,640,324,0,0,960,486]);
  assert.deepEqual(draws[1].slice(1), [0,444,640,324,0,495,314,159]);
});

test('block previews and shared replay both preserve the saved camera layout', () => {
  assert.match(source, /yamRecordingView\?\.\(player, run.camera_order, run.video_layout\)/);
  assert.match(source, /yamRecordingView\?\.\(video, run.camera_order, run.video_layout\)/);
});

test('cached metadata does not recrop the new renderer geometry', () => {
  const events = {};
  const canvas = {hidden:false,setAttribute(){},getContext(){return {drawImage(){throw Error('Already composed');}}}};
  const context = {window:{}, document:{createElement(){return canvas;},addEventListener(){}},
    IntersectionObserver:class {observe(){}}, cancelAnimationFrame(){}};
  vm.runInNewContext(renderer, context);
  const video = {readyState:2, videoWidth:1296, videoHeight:1020, paused:true, after(){},
    classList:{add(){throw Error('Source must remain visible');}},addEventListener(name,fn){events[name]=fn;}};
  context.window.yamRecordingView(video, ['observer','left','top','right']);
  events.loadeddata();
  assert.equal(canvas.hidden, true);
});
