const test = require('node:test');
const assert = require('node:assert/strict');
const progress = require('../static/cag-progress.js');
test('cold start explains delay, elapsed time and cancellation before queue admission', () => {
 const s=progress({status:'preparing',provider:{warmup:'warming',warmup_elapsed_s:73}});
 assert.equal(s.phase,'starting'); assert.match(s.text,/1:13 elapsed/);
 assert.match(s.text,/join the queue when the model is ready/);assert.match(s.text,/Stop/);
});
test('readiness, queue, physical preparation and running are separate states', () => {
 assert.equal(progress({status:'queued',provider:{warmup:'ready'}}).phase,'queued');
 assert.equal(progress({status:'preparing',session_id:'s'}).phase,'preparing');
 assert.equal(progress({status:'running',session_id:'s'}).phase,'running');
});
test('unavailable service is neutral and startup failure has its actual cause', () => {
 const s=progress({},false);assert.equal(s.phase,'unavailable');assert.doesNotMatch(s.text,/Anonymous|run error/);
 assert.equal(progress({status:'failed',error:'GPU startup timed out'}).text,'GPU startup timed out');
 assert.match(progress({}).text,/available on demand/);
});

test('running retains GPU-ready confirmation and person; terminal state explains replay', () => {
 assert.match(progress({status:'running',runner_name:'Andrew'}).text,/GPU ready.*Andrew/);
 assert.match(progress({status:'timed_out',runner_name:'Andrew'}).text,/Andrew.*finished.*recording/);
});

test('elapsed duration waits for authoritative stop instead of inventing completion', () => {
 const s=progress({status:'running',run_elapsed_s:61,run_duration_s:60});
 assert.equal(s.phase,'finishing');assert.match(s.text,/waiting for the robot to confirm/);
});
