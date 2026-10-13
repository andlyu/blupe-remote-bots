const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createRobotAudio} = require('../static/robot-audio.js');
function fixture(play = () => Promise.resolve()) {
  const audio = {muted:true, srcObject:null, play, pause() {}}, status = {};
  const button = {setAttribute(key,value) {this[key]=value;}, addEventListener(_,fn) {this.click=fn;}};
  const readers = [], stopped = [];
  const control = createRobotAudio({audio,button,status,streamFor: robot => ({a:'audio-a',b:'audio-b'})[robot],
    createReader(path, callbacks) {const r={path,...callbacks,close(){this.closed=true;}};readers.push(r);return r;}});
  const track = () => ({kind:'audio',stop(){stopped.push(this);}});
  const deliver = (reader=readers.at(-1)) => {const t=track();reader.onTrack({track:t,streams:[{getTracks:()=>[t]}]});return t;};
  return {audio,button,status,readers,control,deliver,stopped};
}
test('opt-in audio closes and mutes immediately on robot switch; late tracks cannot leak', async () => {
  const f=fixture();f.control.select('a');
  assert.equal(f.readers.length,0);assert.equal(f.audio.muted,true);
  f.button.click();f.deliver();await Promise.resolve();
  assert.equal(f.status.textContent,'Robot audio live');
  f.control.select('b');assert.equal(f.readers[0].closed,true);assert.equal(f.audio.muted,true);
  assert.equal(f.audio.srcObject,null);assert.equal(f.stopped.length,1);
  f.deliver(f.readers[0]);assert.equal(f.stopped.length,2);assert.equal(f.audio.srcObject,null);
  f.button.click();assert.equal(f.readers[1].path,'audio-b');
  f.button.click();assert.equal(f.readers[1].closed,true);
});
test('unavailable, reconnect, and blocked autoplay do not falsely claim live audio', async () => {
  const f=fixture(() => Promise.reject(new Error('blocked')));
  f.control.select('unknown');assert.equal(f.button.disabled,true);f.button.click();assert.equal(f.readers.length,0);
  f.control.select('a');f.button.click();f.readers[0].onError();assert.match(f.status.textContent,/unavailable/);
  f.deliver();await Promise.resolve();assert.equal(f.audio.muted,true);assert.match(f.status.textContent,/blocked/);
  assert.equal(f.readers[0].closed,true);
});
