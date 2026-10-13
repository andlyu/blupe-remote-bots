const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createRobotAudio} = require('../static/robot-audio.js');
const tick=async()=>{await Promise.resolve();await Promise.resolve();};
function fixture({enabled=true,visible=true,play=()=>Promise.resolve()}={}) {
 const button={setAttribute(k,v){this[k]=v;},addEventListener(_,fn){this.click=fn;}},status={},choices=[];
 const control=createRobotAudio({button,status,enabled,visible,remember:x=>choices.push(x),streamFor:r=>({a:'video-a',b:'video-b'})[r]});
 const video={muted:true,srcObject:{},playCalls:0,play(){this.playCalls++;return play(this);}};
 return {button,status,control,video,choices};
}
test('default-on uses the camera element and reports live only after play resolves',async()=>{
 let resolve;const f=fixture({play:()=>new Promise(r=>{resolve=r;})});f.control.select('a');
 f.control.attach(f.video,'a','video-a',true);assert.equal(f.video.muted,false);assert.equal(f.button['aria-pressed'],'false');
 resolve();await tick();assert.equal(f.status.textContent,'Robot audio live');
 f.control.attach(f.video,'a','video-a',true);assert.equal(f.video.playCalls,1);
});
test('blocked audible autoplay restores muted video and retries directly on click',async()=>{
 const f=fixture({play:v=>v.playCalls===1?Promise.reject(Object.assign(new Error(),{name:'NotAllowedError'})):Promise.resolve()});
 f.control.select('a');f.control.attach(f.video,'a','video-a',true);await tick();
 assert.equal(f.button.textContent,'Enable audio');assert.equal(f.video.muted,true);assert.equal(f.video.playCalls,2);
 assert.equal(f.status.textContent,'Audio needs a click');f.button.click();assert.equal(f.video.playCalls,3);await tick();
 assert.equal(f.status.textContent,'Robot audio live');assert.equal(f.video.muted,false);
});
test('robot switching immediately mutes previous video and rejects stale/incorrect source bindings',async()=>{
 const f=fixture();f.control.select('a');f.control.attach(f.video,'a','video-a',true);await tick();
 f.control.select('b');assert.equal(f.video.muted,true);f.control.attach(f.video,'a','video-a',true);
 assert.equal(f.video.muted,true);assert.equal(f.status.textContent,'Waiting for robot audio');
 const next={...f.video,srcObject:{}};f.control.attach(next,'b','video-a',true);assert.equal(next.muted,true);
 f.control.attach(next,'b','video-b',true);await tick();assert.equal(next.muted,false);assert.equal(f.video.muted,true);
});
test('explicit and saved mute survive selection, reconnect and visibility changes',async()=>{
 const f=fixture();f.control.select('a');f.control.attach(f.video,'a','video-a',true);await tick();f.button.click();
 assert.deepEqual(f.choices,[false]);f.control.select('b');f.control.attach(f.video,'b','video-b',true);
 f.control.setVisible(false);f.control.setVisible(true);f.control.refresh();assert.equal(f.video.muted,true);
 const m=fixture({enabled:false});m.control.select('a');m.control.attach(m.video,'a','video-a',true);assert.equal(m.video.playCalls,0);
 f.button.click();await tick();assert.equal(f.video.muted,false);assert.deepEqual(f.choices,[false,true]);
});
test('visibility pauses sound; return and replaced media honor enabled intent',async()=>{
 const f=fixture();f.control.select('a');f.control.attach(f.video,'a','video-a',true);await tick();
 f.control.setVisible(false);assert.equal(f.video.muted,true);f.control.detach(f.video);f.control.setVisible(true);
 const next={...f.video,srcObject:{}};f.control.attach(next,'a','video-a',true);await tick();assert.equal(next.muted,false);
 f.control.detach(f.video);assert.equal(next.muted,false);
});
test('late play rejection/resolution cannot alter a new robot or muted intent',async()=>{
 let reject;const f=fixture({play:()=>new Promise((_,r)=>{reject=r;})});f.control.select('a');f.control.attach(f.video,'a','video-a',true);
 f.control.select('b');reject(Object.assign(new Error(),{name:'NotAllowedError'}));await tick();assert.equal(f.button.textContent,'Mute');assert.equal(f.video.muted,true);
});
test('missing audio keeps video muted; later audio and storage intent changes apply without a second player',async()=>{
 const f=fixture();f.control.select('a');f.control.attach(f.video,'a','video-a',false);assert.equal(f.video.playCalls,0);
 f.control.attach(f.video,'a','video-a',true);await tick();assert.equal(f.video.muted,false);
 f.control.setEnabled(false);assert.equal(f.video.muted,true);assert.deepEqual(f.choices,[]);
 f.control.select('unknown');assert.equal(f.button.disabled,true);
});
