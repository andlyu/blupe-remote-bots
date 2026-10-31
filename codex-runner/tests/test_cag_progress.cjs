const test = require('node:test');
const assert = require('node:assert/strict');
const progress = require('../static/cag-progress.js');
test('cold start explains delay, elapsed time and cancellation before queue admission', () => {
 const s=progress({status:'preparing',provider:{warmup:'warming',gpu_startup:{launch_required:true,launch_started_at:100}}},true,173);
 assert.equal(s.phase,'starting'); assert.match(s.text,/73.0s elapsed/);
 assert.match(s.text,/join the queue when the model is ready/);assert.match(s.text,/Stop/);
});
test('readiness, queue, physical preparation and running are separate states', () => {
 assert.equal(progress({status:'queued',provider:{warmup:'ready'}}).phase,'queued');
 assert.equal(progress({status:'preparing',session_id:'s'}).phase,'preparing');
 assert.equal(progress({status:'running',session_id:'s',run_metrics:{confirmed_waypoints:1}}).phase,'running');
});
test('unavailable service is neutral and startup failure has its actual cause', () => {
 const s=progress({},false);assert.equal(s.phase,'unavailable');assert.doesNotMatch(s.text,/Anonymous|run error/);
 assert.equal(progress({status:'failed',error:'GPU startup timed out'}).text,'GPU startup timed out');
 assert.match(progress({}).text,/available on demand/);
});

test('running retains GPU-ready confirmation and person; terminal state explains replay', () => {
 assert.match(progress({status:'running',runner_name:'Andrew',run_metrics:{confirmed_waypoints:1}}).text,/GPU ready.*Andrew/);
 assert.match(progress({status:'timed_out',runner_name:'Andrew'}).text,/Andrew.*finished.*recording/);
});

test('elapsed duration waits for authoritative stop instead of inventing completion', () => {
 const s=progress({status:'running',run_elapsed_s:61,run_duration_s:60});
 assert.equal(s.phase,'finishing');assert.match(s.text,/waiting for the robot to confirm/);
});

test('warm and unknown availability never claim a cold GPU launch', () => {
 for (const available of [false, null]) {
  const s=progress({status:'preparing',provider:{gpu_startup:{launch_required:available}}});
  assert.equal(s.phase,'checking'); assert.doesNotMatch(s.text,/Starting GPU/);
 }
});
test('Home confirmation and sent packets do not claim method motion', () => {
 const s=progress({status:'running',commands_submitted:10,packets_submitted:1,
   cag_startup:{home:{completed_at:100}},run_metrics:{confirmed_waypoints:0}},true,116);
 assert.equal(s.phase,'first_action'); assert.match(s.text,/16.0s since Home/);
 assert.match(s.text,/longer than the 15s target/); assert.doesNotMatch(s.text,/reports.*progress/);
});
test('completed GPU, queue and Home stages retain actual timestamps after completion', () => {
 const s=progress({status:'timed_out',cag_startup:{gpu:{launch_required:true,launch_started_at:100,ready_at:114},
   queue:{entered_at:115,admitted_at:126},home:{completed_at:127}}});
 assert.equal(s.stages.length,5);assert.match(s.stages[1],/startup 14.0s/);
 assert.match(s.stages[2],/queue entered/);assert.match(s.stages[3],/admission confirmed/);
 assert.match(s.stages[4],/settled at Home/);
});
