const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('actual UI serializes the fixed brightness into the ordinary run request', async () => {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: id === '#imageBrightness' ? '50' : '', textContent: '', handlers: {},
      addEventListener(event, callback) {this.handlers[event] = callback;},
      replaceChildren() {},
      after() {}, setAttribute() {},
    });
    return elements.get(id);
  }
  const panel = {setAttribute() {}, querySelector: element};
  const document = {
    readyState: 'complete',
    createElement(tag) {return tag === 'p' ? element('#dreamConnectionNotice') : panel;},
    querySelector(selector) {
      if (selector === '.watchLayout') return {before() {}};
      if (selector === '#meetingWorkspace' || selector === '#brightnessOpen') return null;
      return element(selector);
    },
  };
  const sent = [];
  let statusState = {status:'stopped', error:'RuntimeError: Dream request failed (DreamProtocolError; connection_failure; RemoteDisconnected; response_headers)'};
  const context = {document, location: {href:'http://127.0.0.1:8798/', origin:'http://127.0.0.1:8798'}, URL,
    window: {fetch: async (url, options) => {sent.push({url, options}); return new Response(JSON.stringify(statusState));}}};
  vm.runInNewContext(fs.readFileSync(__dirname + '/brightness.js', 'utf8'), context);
  async function launch() {
    const options = {method:'POST', headers:{'X-Yam-CSRF':'preserved'},
      body:JSON.stringify({provider:'dream', prompt:'same task', run_duration_s:120})};
    await context.window.fetch('/api/run', options);
    return sent.at(-1);
  }
  let request = await launch();
  assert.equal(JSON.parse(request.options.body).image_brightness, .5);
  assert.equal(request.options.headers['X-Yam-CSRF'], 'preserved');
  element('#brightnessBaseline').handlers.click();
  assert.equal(JSON.parse((await launch()).options.body).image_brightness, 1);
  element('#imageBrightness').value = '51';
  element('#imageBrightness').handlers.input();
  const priorBody = sent.at(-1).options.body;
  assert.equal(JSON.parse((await launch()).options.body).image_brightness, .51);
  assert.equal(JSON.parse(priorBody).image_brightness, 1);
  assert.match(element('#brightnessRunSetting').textContent, /Submitted run: 51%/);
  element('#brightnessDark').handlers.click();
  assert.equal(JSON.parse((await launch()).options.body).image_brightness, .5);
  const before = sent.length;
  const response = await context.window.fetch('/api/status', {method:'GET'});
  assert.equal(sent.at(-1).options.body, undefined);
  assert.equal(sent.length, before + 1); // Reading a failure must not retry a run.
  assert.equal(response.bodyUsed, false);
  assert.deepEqual(await response.json(), statusState);
  assert.equal(element('#dreamConnectionNotice').hidden, false);
  assert.match(element('#dreamConnectionNotice').textContent, /Dream connection interrupted/);
  statusState = {status:'running', error:null};
  await context.window.fetch('/api/status', {method:'GET'});
  assert.equal(element('#dreamConnectionNotice').hidden, true);
  statusState = {status:'stopped',error:'Calibration error'};
  await context.window.fetch('/api/status', {method:'GET'});
  assert.equal(element('#dreamConnectionNotice').hidden, true);
});
