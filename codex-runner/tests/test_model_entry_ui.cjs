const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(process.env.PLAYGROUND_ENTRY_SOURCE || __dirname + '/../static/hosted.js', 'utf8');
const helper = source.slice(source.indexOf('function playgroundEntryModel('), source.indexOf('function createRunVideoEmailControl('));
const select = vm.runInNewContext(helper + '\nplaygroundEntryModel', {URLSearchParams});
const choices = (...values) => values.map(value => typeof value === 'string' ? {value} : value);
const entry = (query, options, session) => JSON.parse(JSON.stringify(select(query, options, session)));

test('public entry prefers Dream beta where available, with Astra for other stations', () => {
  for (const query of ['', '?model=unknown', '?model=__proto__']) {
    assert.deepEqual(entry(query, choices('hosted_aspire', 'guest_astra', 'dream_flash', 'dream')),
      {provider:'dream', model:'dreamlabs/dream-1-beta'});
  }
  for (const dream of [{value:'dream', hidden:true}, {value:'dream', disabled:true}]) {
    assert.deepEqual(entry('', choices('guest_astra', dream)),
      {provider:'guest_astra', model:'gpt-6-astra'});
  }
  assert.deepEqual(entry('', choices('hosted_aspire', 'guest_gemini', 'guest_astra')),
    {provider:'guest_astra', model:'gpt-6-astra'});
  assert.deepEqual(entry('', choices('guest_gemini', 'openai')),
    {provider:'openai', model:'gpt-6-astra'});
});

test('explicit model links override Dream and Dream links use only an available provider', () => {
  const options = choices('dream', 'dream_flash', 'guest_astra', 'guest_gemini');
  assert.deepEqual(entry('?model=astra', options), {provider:'guest_astra', model:'gpt-6-astra'});
  assert.deepEqual(entry('?model=argon', options), {provider:'guest_gemini', model:'gemini-4-argon'});
  for (const model of ['dream', 'dream-1', 'dreamlabs/dream-1-beta']) {
    assert.deepEqual(entry('?model=' + model, options), {provider:'dream', model:'dreamlabs/dream-1-beta'});
  }
  assert.equal(entry('?model=dream', choices('dream_flash')), null);
  assert.equal(entry('', options, {local_runner:true}), null);
  assert.equal(entry('', options, {station_local:true}), null);
});

test('Argon share links select the existing sponsored route and compose with robot links', () => {
  for (const value of ['argon', 'Argon', 'gemini-4-argon']) {
    assert.deepEqual(entry('?robot_id=yam-1&model=' + value, choices('guest_astra', 'guest_gemini')),
      {provider:'guest_gemini', model:'gemini-4-argon'});
  }
});

test('Terra share links select the exact model through available existing routes', () => {
  for (const value of ['terra', 'Terra', 'gpt-6.1-terra']) {
    assert.deepEqual(entry('?robot_id=yam-1&model=' + value, choices('dream','guest_astra','openai')),
      {provider:'guest_astra', model:'gpt-6.1-terra'});
  }
  assert.deepEqual(entry('?model=terra', choices('codex','openai'), {local_runner:true}),
    {provider:'codex', model:'gpt-6.1-terra'});
  assert.deepEqual(entry('?model=terra', choices('openai')),
    {provider:'openai', model:'gpt-6.1-terra'});
  assert.equal(entry('?model=terra', choices('dream',{value:'guest_astra',disabled:true})), null);
  assert.equal(entry('?model=terra', choices('codex'), {local_runner:true,
    configured_providers:{codex:{model:'gpt-6-astra'}}}), null);
  assert.equal(entry('?model=terra', choices('codex'), {station_local:true}), null);
});

test('unknown and unavailable models fall back to available Astra, never enabling a provider', () => {
  for (const query of ['?model=unknown', '?model=__proto__', '?model=', '?model=argon']) {
    assert.deepEqual(entry(query, choices('guest_astra', {value:'guest_gemini', disabled:true})),
      {provider:'guest_astra', model:'gpt-6-astra'});
  }
  assert.equal(entry('?model=argon', choices({value:'gemini', hidden:true})), null);
});

test('local launchers retain their default unless the link explicitly selects an available model', () => {
  const options = choices('codex', 'claude', 'gemini');
  for (const query of ['', '?model=unknown', '?model=__proto__']) {
    assert.equal(entry(query, options, {local_runner:true}), null);
  }
  assert.deepEqual(entry('?model=argon', options, {local_runner:true}),
    {provider:'gemini', model:'gemini-4-argon'});
  assert.deepEqual(entry('?model=astra', options, {local_runner:true}),
    {provider:'codex', model:'gpt-6-astra'});
  assert.equal(entry('?model=argon', choices('codex'), {local_runner:true}), null);
  assert.equal(entry('?model=argon', options, {local_runner:true,
    configured_providers:{gemini:{model:'gemini-custom'}}}), null);
  assert.equal(entry('?model=argon', options, {station_local:true}), null);
});

test('startup sets provider and model together, overriding an old saved model without launching', () => {
  const start = source.indexOf('      const entryModel = playgroundEntryModel(');
  const block = source.slice(start, source.indexOf('      buttons();', start));
  const nodes = {provider:{value:'hosted_aspire', options:choices('hosted_aspire','guest_gemini','openai')}, model:{value:'gpt-6.1-sol'}};
  const events = [], selections = [];
  const context = {
    playgroundEntryModel:select, location:{search:''}, $:id=>nodes[id], session:{}, lastLive:null,
    providerChanged() { nodes.model.value = nodes.provider.value === 'guest_gemini' ? 'gemini-4-argon' : 'gpt-6.1-sol'; },
    window:{yamModelPicker:{selectModel(value) { selections.push(value); nodes.model.value=value; }}},
    document:{dispatchEvent(event) { events.push(event.type); }}, Event:class { constructor(type) { this.type=type; } },
    applyModelName() {}
  };
  vm.runInNewContext(block, context);
  assert.equal(nodes.provider.value, 'openai');
  assert.equal(nodes.model.value, 'gpt-6-astra');
  assert.deepEqual(selections, ['gpt-6-astra']);
  assert.deepEqual(events, ['blupe-model-changed']);

  context.location.search='?model=argon';
  vm.runInNewContext(block, {...context});
  assert.equal(nodes.provider.value, 'guest_gemini');
  assert.equal(nodes.model.value, 'gemini-4-argon');
  context.location.search='?model=terra';
  vm.runInNewContext(block, {...context});
  assert.equal(nodes.provider.value, 'openai');
  assert.equal(nodes.model.value, 'gpt-6.1-terra');
  assert.equal(selections.at(-1), 'gpt-6.1-terra');
  // The link is an initial choice only; normal provider changes remain possible.
  nodes.provider.value='openai';context.providerChanged();
  assert.equal(nodes.provider.value,'openai');
});
