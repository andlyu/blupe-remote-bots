const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createModelPicker} = require('../static/model-picker.js');
const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture(api = async () => ({models:[],source:'provider',message:'Refreshed'}), storage = new Map()) {
  const nodes = {};
  const $ = id => nodes[id] ||= {value:'',disabled:false,hidden:false,children:[],listeners:{},
    ownerDocument:{createElement:()=>({})},
    addEventListener(event, fn) {this.listeners[event] = fn;},
    replaceChildren(...children) {this.children = children;}};
  let context = 'robot-1';
  const picker = createModelPicker({$,api,storage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},context:()=>context});
  const choose = (name, fixed=false) => {
    picker.saveSelection(); $('provider').value=name; $('model').value='provider-default'; picker.providerChanged({fixed});
  };
  const input = value => {$('model').value=value; $('model').listeners.input();};
  return {$,picker,choose,input,storage,context:value=>context=value};
}
test('new provider models appear without changing the selected model', async () => {
  const f=fixture(async()=>({models:[{id:'gpt-6.1-sol',label:'Sol 6.1'},{id:'gpt-7-sol',label:'Sol 7'}],source:'provider',message:'Refreshed'}));
  f.choose('codex'); f.input('gpt-6.1-sol'); await tick();
  assert.equal(f.$('model').value,'gpt-6.1-sol');
  assert.deepEqual(f.$('availableModels').children.map(x=>x.value),['gpt-6.1-sol','gpt-7-sol']);
  f.choose('claude'); f.input('claude-opus-6'); f.choose('codex');
  assert.equal(f.$('model').value,'gpt-6.1-sol');
  f.choose('codex'); assert.equal(f.$('model').value,'gpt-6.1-sol');
  const restored=fixture(undefined,f.storage);restored.choose('claude');
  assert.equal(restored.$('model').value,'claude-opus-6');
});
test('catalog and reasoning options follow the current provider and ignore stale responses',async()=>{
  const pending=[];const f=fixture((path,payload)=>new Promise(resolve=>pending.push({payload,resolve})));
  f.choose('codex'); f.choose('claude');
  pending[1].resolve({models:[{id:'claude-opus-5-5',label:'Opus',reasoning_efforts:['high','max']}],source:'provider',message:'Claude models'});
  await tick(); pending[0].resolve({models:[{id:'gpt-7-sol',label:'Sol'}],source:'provider',message:'Wrong provider'});await tick();
  assert.equal(f.$('availableModels').children[0].value,'claude-opus-5-5');
  assert.equal(f.$('modelCatalogStatus').textContent,'Claude models');
  assert.equal(f.$('reasoningEffort').value,'high');
  assert.deepEqual(f.$('reasoningEffort').children.map(x=>x.value),['high','max']);
  f.choose('codex'); f.context('robot-2');
  pending[2].resolve({models:[{id:'gpt-8-sol'}],source:'provider',message:'Old session'});await tick();
  assert.notEqual(f.$('modelCatalogStatus').textContent,'Old session');
});
test('failed refresh preserves fetched choices and a manually entered future model',async()=>{
  let fail=false;
  const f=fixture(async()=>fail?{models:[{id:'gpt-6-astra'}],source:'fallback',message:'Refresh failed'}:
    {models:[{id:'gpt-6.1-sol'}],source:'provider',message:'Models'});
  f.choose('codex');await tick();f.input('gpt-8-sol');fail=true;await f.picker.refresh(true);
  assert.equal(f.$('model').value,'gpt-8-sol');
  assert.equal(f.$('availableModels').children[0].value,'gpt-6.1-sol');
  assert.equal(f.$('modelCatalogStatus').textContent,'Refresh failed');
});
test('fixed policies do not discover models; subscription discovery never includes API keys',async()=>{
  const calls=[];const f=fixture(async(path,payload)=>{calls.push(payload);return {models:[],source:'provider'};});
  f.$('apiKey').value='private-key';f.choose('groot',true);await tick();
  assert.equal(calls.length,0);assert.equal(f.$('modelSettings').hidden,true);
  f.choose('codex');await tick();assert.equal(calls[0].api_key,undefined);
  f.choose('openai');await tick();assert.equal(calls[1].api_key,'private-key');
  assert(!JSON.stringify([...f.storage]).includes('private-key'));
});
test('BluPe Claude models are discovered without keys and remembered separately from API models',async()=>{
  const calls=[];const f=fixture(async(path,payload)=>{calls.push(payload);return {models:[{id:'claude-opus-5-6',label:'Opus 5.6'}],source:'claude_subscription'};});
  f.$('apiKey').value='private-key';f.choose('guest_claude');await tick();
  assert.deepEqual(calls[0],{provider:'guest_claude'});
  assert.equal(f.$('modelSettings').hidden,false);
  f.input('claude-opus-5-6');f.choose('anthropic');f.choose('guest_claude');
  assert.equal(f.$('model').value,'claude-opus-5-6');
});
test('reasoning bar maps Extra High to xhigh and remembers effort per provider and model',async()=>{
  const f=fixture(async(_path,payload)=>({source:'provider',models:payload.provider==='codex'
    ? [{id:'gpt-6.1-sol',label:'GPT-6.1 Sol',reasoning_efforts:['low','medium','high','xhigh','max'],default_reasoning_effort:'medium'}]
    : [{id:'claude-opus-5-5',label:'Claude Opus 5.5',reasoning_efforts:['low','medium','high','xhigh','max'],default_reasoning_effort:'medium'}]}));
  f.choose('codex');await tick();f.input('gpt-6.1-sol');
  assert.equal(f.$('reasoningEffort').value,'medium');
  f.$('reasoningLevel').value='3';f.$('reasoningLevel').listeners.input();
  assert.equal(f.$('reasoningEffort').value,'xhigh');
  assert.equal(f.$('reasoningLabel').textContent,'Extra High');
  assert.equal(f.$('reasoningModel').textContent,'GPT-6.1 Sol');
  f.choose('claude');await tick();assert.equal(f.$('reasoningEffort').value,'medium');
  f.choose('codex');assert.equal(f.$('reasoningEffort').value,'xhigh');
  f.input('gpt-6-astra');assert.equal(f.$('reasoningEffort').value,'low');
  f.input('gpt-6.1-sol');assert.equal(f.$('reasoningEffort').value,'xhigh');
  f.$('resetReasoning').listeners.click();assert.equal(f.$('reasoningEffort').value,'medium');
});
test('sponsored Astra keeps its model fixed while discovering supported effort levels',async()=>{
  const calls=[];const f=fixture(async(path,payload)=>{calls.push(payload);return {source:'codex_subscription',
    models:[{id:'gpt-6-astra',label:'GPT-6 Astra',reasoning_efforts:['high','xhigh'],default_reasoning_effort:'high'}]};});
  f.$('provider').value='guest_astra';f.picker.providerChanged({fixedModel:true});await tick();
  assert.equal(f.$('modelSettings').hidden,true);assert.equal(f.$('reasoningBar').hidden,false);
  assert.deepEqual(calls,[{provider:'guest_astra'}]);
  assert.equal(f.$('reasoningLevel').max,'1');
  f.$('reasoningLevel').value='1';f.$('reasoningLevel').listeners.input();
  assert.equal(f.$('reasoningEffort').value,'xhigh');
});


test('Haiku suggestions and discovered future versions retain the subscription provider and model effort',async()=>{
  const f=fixture(async()=>({source:'claude_subscription',models:[
    {id:'claude-opus-5-5',label:'Opus 5.5'},
    {id:'claude-haiku-5-5',label:'Haiku 5.5',reasoning_efforts:['low','medium','high','xhigh','max'],default_reasoning_effort:'medium'},
    {id:'claude-haiku-6',label:'Haiku 6'}]}));
  assert.deepEqual(f.picker.modelsFor('guest_claude').map(row=>row.id),['claude-opus-5-5','claude-haiku-5-5']);
  assert.deepEqual(f.picker.modelsFor('groot'),[]);
  f.choose('guest_claude');await tick();
  assert.deepEqual(f.picker.modelsFor('guest_claude').map(row=>row.id),['claude-opus-5-5','claude-haiku-5-5','claude-haiku-6']);
  f.picker.selectModel('claude-haiku-5-5');
  assert.equal(f.$('provider').value,'guest_claude');
  assert.equal(f.$('model').value,'claude-haiku-5-5');
  f.$('resetReasoning').listeners.click();assert.equal(f.$('reasoningEffort').value,'medium');
  f.$('reasoningLevel').value='3';f.$('reasoningLevel').listeners.input();assert.equal(f.$('reasoningEffort').value,'xhigh');
  f.choose('codex');f.choose('guest_claude');
  assert.equal(f.$('model').value,'claude-haiku-5-5');
  assert.equal(f.$('reasoningEffort').value,'xhigh');
});
