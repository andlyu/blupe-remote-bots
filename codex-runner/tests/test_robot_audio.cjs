const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createRobotAudio} = require('../static/robot-audio.js');
function fixture({play = () => Promise.resolve(), enabled = true, visible = true} = {}) {
  const audio = {muted:true, srcObject:null, play, pause() {}}, status = {};
  const button = {setAttribute(key,value) {this[key]=value;}, addEventListener(_,fn) {this.click=fn;}};
  const readers = [], stopped = [], choices = [];
  const control = createRobotAudio({audio,button,status,enabled,visible,remember:value=>choices.push(value),
    streamFor: robot => ({a:'audio-a',b:'audio-b'})[robot],
    createReader(path, callbacks) {const r={path,...callbacks,close(){this.closed=true;}};readers.push(r);return r;}});
  const track = () => ({kind:'audio',stop(){stopped.push(this);}});
  const deliver = (reader=readers.at(-1)) => {const t=track();reader.onTrack({track:t,streams:[{getTracks:()=>[t]}]});return t;};
  return {audio,button,status,readers,control,deliver,stopped,choices};
}
const tick = () => Promise.resolve();
test('defaults on but reports live only after play resolves; switch closes old audio before new track', async () => {
  let resolve; const f=fixture({play:()=>new Promise(r=>{resolve=r;})});f.control.select('a');
  assert.equal(f.readers.length,1);assert.match(f.status.textContent,/Connecting/);
  f.deliver();assert.equal(f.button['aria-pressed'],'false');
  resolve();await tick();assert.equal(f.status.textContent,'Robot audio live');
  f.control.select('b');assert.equal(f.readers[0].closed,true);assert.equal(f.audio.muted,true);
  assert.equal(f.audio.srcObject,null);assert.equal(f.stopped.length,1);
  assert.equal(f.readers[1].path,'audio-b');
  f.deliver(f.readers[0]);assert.equal(f.stopped.length,2);assert.equal(f.audio.srcObject,null);
  f.control.select('b');assert.equal(f.readers.length,2);
});
test('blocked autoplay retains one stream for direct click retry, never falsely reporting live', async () => {
  let calls=0;
  const f=fixture({play:()=>++calls===1 ? Promise.reject(Object.assign(new Error(),{name:'NotAllowedError'})) : Promise.resolve()});
  f.control.select('a');f.deliver();await tick();
  assert.equal(f.button.textContent,'Enable audio');assert.equal(f.audio.muted,true);
  assert.equal(f.button['aria-pressed'],'false');assert.equal(f.status.textContent,'Audio needs a click');
  assert.ok(f.audio.srcObject);assert.notEqual(f.readers[0].closed,true);
  f.button.click();assert.equal(calls,2);await tick();
  assert.equal(f.readers.length,1);assert.equal(f.audio.muted,false);assert.equal(f.status.textContent,'Robot audio live');
});
test('explicit mute persists as intent across selection, metadata refresh and hide/show', async () => {
  const f=fixture();f.control.select('a');f.deliver();await tick();f.button.click();
  assert.deepEqual(f.choices,[false]);assert.equal(f.audio.muted,true);assert.equal(f.audio.srcObject,null);
  f.control.select('b');f.control.refresh();f.control.setVisible(false);f.control.setVisible(true);
  assert.equal(f.readers.length,1);assert.equal(f.button.textContent,'Unmute');
  f.button.click();assert.deepEqual(f.choices,[false,true]);assert.equal(f.readers[1].path,'audio-b');
});
test('saved mute skips startup; enabled visibility resume creates only one new reader', () => {
  const muted=fixture({enabled:false});muted.control.select('a');assert.equal(muted.readers.length,0);
  const f=fixture();f.control.select('a');f.control.setVisible(false);
  assert.equal(f.readers[0].closed,true);assert.equal(f.audio.muted,true);
  f.control.select('b');assert.equal(f.readers.length,1);
  f.control.setVisible(true);f.control.setVisible(true);assert.equal(f.readers.length,2);
  assert.equal(f.readers[1].path,'audio-b');
});
test('late play rejection or resolution cannot change a newer robot or explicit mute', async () => {
  let resolve,reject;const f=fixture({play:()=>new Promise((r,j)=>{resolve=r;reject=j;})});
  f.control.select('a');f.deliver();f.control.select('b');reject(Object.assign(new Error(),{name:'NotAllowedError'}));await tick();
  assert.equal(f.status.textContent,'Connecting audio…');assert.equal(f.button.textContent,'Mute');
  f.deliver();f.button.click();resolve();await tick();assert.equal(f.status.textContent,'Robot audio muted');
});
test('reader retry clears failed tracks and respects subsequent mute; unsupported robots stay disconnected', async () => {
  const f=fixture();f.control.select('unknown');assert.equal(f.button.disabled,true);assert.equal(f.readers.length,0);
  f.control.select('a');f.deliver();await tick();f.readers[0].onError();
  assert.equal(f.audio.srcObject,null);assert.equal(f.audio.muted,true);assert.match(f.status.textContent,/unavailable/);
  f.deliver();await tick();assert.equal(f.status.textContent,'Robot audio live');assert.equal(f.readers.length,1);
  f.button.click();f.readers[0].onError();f.deliver();await tick();
  assert.equal(f.audio.srcObject,null);assert.equal(f.status.textContent,'Robot audio muted');
});
test('storage-driven mute updates the current page without overwriting preferences', () => {
  const f=fixture();f.control.select('a');f.control.setEnabled(false);
  assert.equal(f.readers[0].closed,true);assert.deepEqual(f.choices,[]);
  f.control.setEnabled(true);assert.equal(f.readers.length,2);
});
