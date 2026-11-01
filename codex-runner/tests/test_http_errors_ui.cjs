const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict'), test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../static/hosted.js'), 'utf8');

function fixture(reply) {
  const calls = [], key = {value:'retained-key'};
  const c = vm.createContext({robotGeneration:1, csrf:'token', selectedRobot:'robo-house', liveViewers:null,
    ended:false, buttons(){}, $:()=>key,
    fetch:async (...args)=>{calls.push(args); return typeof reply === 'function' ? reply() : reply;}});
  let start = source.indexOf('function createRunLaunchGuard(');
  vm.runInContext(source.slice(start, source.indexOf("(() => {\n  'use strict';", start)) +
    '\nvar runLaunchGuard = createRunLaunchGuard();', c);
  start = source.indexOf('  async function api(');
  vm.runInContext(source.slice(start, source.indexOf('  const runVideoEmail', start)), c);
  return {c, calls, key};
}

test('status heartbeats use the selected robot and the live camera visibility', async ()=>{
  for(const watching of [true,false]) {
    const f=fixture(Response.json({status:'idle'}));
    f.c.liveViewers={watching:()=>watching};
    await f.c.api('/api/status');
    assert.equal(f.calls[0][1].headers['X-YAM-Watching'],watching?'1':'0');
    assert.equal(f.calls[0][1].headers['X-Blupe-Robot'],'robo-house');
    assert.equal(f.calls[0][1].method,'GET');
  }
});

test('plain-text maintenance rejection has an actionable error and never replays the run', async ()=>{
  const f = fixture(new Response('Deployment in progress. Please retry shortly.', {status:503}));
  await assert.rejects(f.c.api('/api/run', {prompt:'place green block on plate'}), error=>{
    assert.match(error.message, /temporarily unavailable.*HTTP 503.*try again shortly/i);
    assert.doesNotMatch(error.message, /Unexpected token|valid JSON/);
    return true;
  });
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0][1].method, 'POST');
  assert.equal(f.c.ended, false);
});

test('proxy HTML and empty error bodies retain status without displaying raw content', async ()=>{
  for (const [status, body] of [[502,'<html>private proxy diagnostic</html>'], [504,''], [400,'private diagnostic']]) {
    const f = fixture(new Response(body, {status}));
    await assert.rejects(f.c.api('/api/run', {}), error=>{
      assert.match(error.message, new RegExp('HTTP '+status));
      assert.doesNotMatch(error.message, /private|html|Unexpected token|valid JSON/);
      return true;
    });
    assert.equal(f.calls.length, 1);
  }
});

test('valid JSON errors preserve the server message and subscription metadata', async ()=>{
  const setup = {state:'login_required'};
  const f = fixture(Response.json({error:'Sign in required', subscription_setup:setup, payment_confirmed:true}, {status:409}));
  await assert.rejects(f.c.api('/api/run', {}), error=>{
    assert.equal(error.message, 'Sign in required');
    assert.equal(error.subscriptionSetup.state, setup.state);
    assert.equal(error.paymentConfirmed, true);
    return true;
  });
});

test('a non-JSON unauthorized response still expires the session and clears its key', async ()=>{
  const f = fixture(new Response('Unauthorized', {status:401}));
  await assert.rejects(f.c.api('/api/status'), /HTTP 401/);
  assert.equal(f.c.ended, true);
  assert.equal(f.key.value, '');
});

test('malformed successful replies are rejected without resubmitting an uncertain run', async ()=>{
  for (const body of ['Brief maintenance', 'null', '[]', '"not an object"']) {
    const f = fixture(new Response(body, {status:200}));
    await assert.rejects(f.c.api('/api/run', {}), /invalid response.*Check the current run/i);
    assert.equal(f.calls.length, 1);
  }
});

test('invalid successful status replies are reported even after an accepted attempt', async ()=>{
  const f = fixture(new Response('<html>proxy</html>', {status:200}));
  const guard = f.c.runLaunchGuard, version = guard.start();
  guard.accept(version, 'accepted');
  await assert.rejects(f.c.api('/api/status'), error=>{
    assert.equal(error.stale, undefined);
    assert.match(error.message, /invalid response/i);
    return true;
  });
});

test('late non-JSON responses from a previous robot cannot revoke the new session', async ()=>{
  let deliver;
  const f = fixture(()=>new Promise(resolve=>{deliver=resolve;}));
  const pending = f.c.api('/api/status');
  f.c.robotGeneration = 2; f.c.csrf = 'new-token';
  deliver(new Response('Unauthorized', {status:401}));
  await assert.rejects(pending, error=>error.stale === true);
  assert.equal(f.c.ended, false);
  assert.equal(f.key.value, 'retained-key');
});

test('late maintenance rejection cannot replace a newer run attempt', async ()=>{
  let deliver;
  const f = fixture(()=>new Promise(resolve=>{deliver=resolve;}));
  const pending = f.c.api('/api/run', {});
  f.c.runLaunchGuard.start();
  deliver(new Response('Brief maintenance', {status:503}));
  await assert.rejects(pending, error=>error.stale === true);
  assert.equal(f.calls.length, 1);
});

test('valid successful responses still pass through the API unchanged', async ()=>{
  const f = fixture(Response.json({status:'preparing', attempt_id:'new'}));
  const result = await f.c.api('/api/run', {});
  assert.equal(result.status, 'preparing');
  assert.equal(result.attempt_id, 'new');
});
