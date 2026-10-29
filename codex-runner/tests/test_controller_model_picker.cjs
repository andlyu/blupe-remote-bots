const assert = require('node:assert/strict');
const {test} = require('node:test');
const {controllerPayload,automaticControllerModel,createControllerModelPicker} = require('../static/controller-model-picker.js');
const fixed = {provider:'dream_flash',model:'dreamlabs/dream-1-beta-flash',available:true};
assert.deepEqual(controllerPayload(fixed,'dream_flash','',''), {executor:'controller',controller_model:'dream_flash',provider:fixed.provider,model:fixed.model,api_key:'',use_api_depth:false});
const custom = {provider:'custom',user_endpoint:true,available:true};
assert.equal(controllerPayload(custom,'custom','https://example.com/v1/responses','my-model').custom_endpoint.protocol,'responses_v1');
for (const url of ['http://example.com','https://user:password@example.com','https://example.com?key=private'])
  assert.throws(()=>controllerPayload(custom,'custom',url,'my-model'));
assert.throws(()=>controllerPayload({...fixed,available:false},'dream_flash','',''));
console.log('Controller model selection preserves registered checkpoints and validates user endpoints.');

const astra={provider:'openai',model:'gpt-6-astra',label:'Astra',available:true};
const beta={provider:'dream',model:'dreamlabs/dream-1-beta',label:'Dream-1 beta',available:true};
function fixture() {
  const nodes={};
  const $=id=>nodes[id] ||= {value:'',disabled:false,required:false,hidden:false,
    listeners:{},ownerDocument:{createElement:()=>({})},children:[],options:{},
    addEventListener(name,fn){this.listeners[name]=fn;},
    querySelector(selector){return this.options[selector] ||= {};},
    replaceChildren(...children){this.children=children;}};
  $('executionLocation').value='auto';$('provider').value='dream';$('model').value=beta.model;
  let picker;
  const refresh=()=>{for(const id of ['provider','model','apiKey']) $(id).disabled=false;picker.sync();};
  picker=createControllerModelPicker($,refresh);
  const choose=value=>{$('executionLocation').value=value;$('executionLocation').listeners.change();};
  return {$,picker,refresh,choose};
}
test('automatic execution uses the exact available Dream checkpoint and keeps normal model controls usable',()=>{
  const f=fixture();f.picker.configure({astra,dream_one:beta,dream_flash:fixed});
  assert.equal(f.$('executionLocation').value,'auto');
  assert.equal(f.picker.payload().controller_model,'dream_one');
  assert.equal(f.$('provider').disabled,false);assert.equal(f.$('model').disabled,false);
  assert.equal(f.$('controllerModelSettings').hidden,true);
  assert.match(f.$('controllerExecutionHelp').textContent,/Dream-1 beta.*controller/);
  f.$('provider').value='dream_flash';f.$('model').value=fixed.model;f.refresh();
  assert.equal(f.picker.payload().controller_model,'dream_flash');
});
test('unsupported, unavailable and provider-mismatched models retain their normal runner request',()=>{
  const f=fixture();f.picker.configure({astra,dream_one:{...beta,available:false}});
  assert.equal(f.picker.selected(),false);assert.deepEqual(f.picker.payload(),{});
  f.$('provider').value='openai';f.$('model').value='gpt-6.1-terra';f.refresh();
  assert.equal(f.picker.selected(),false);
  for(const provider of ['aspire','hosted_aspire','unknown']) {
    f.$('provider').value=provider;f.$('model').value=astra.model;f.refresh();
    assert.equal(f.picker.selected(),false);
  }
});
test('subscription and sponsored aliases require the exact registered model',()=>{
  const rows={astra,opus:{provider:'anthropic',model:'claude-opus-5-5',available:true},
    argon:{provider:'guest_gemini',model:'gemini-4-argon',available:true}};
  for(const p of ['openai','codex','guest_astra']) assert.equal(automaticControllerModel(rows,p,astra.model)[0],'astra');
  for(const p of ['anthropic','claude','guest_claude']) assert.equal(automaticControllerModel(rows,p,'claude-opus-5-5')[0],'opus');
  for(const p of ['gemini','guest_gemini']) assert.equal(automaticControllerModel(rows,p,'gemini-4-argon')[0],'argon');
  assert.equal(automaticControllerModel(rows,'claude','claude-haiku-5-5'),undefined);
});
test('automatic selection follows robot and readiness updates without replacing the chosen model',()=>{
  const f=fixture();f.picker.configure({dream_one:beta});
  assert.equal(f.picker.selected(),true);
  f.picker.configure({dream_one:{...beta,available:false,reason:'Not provisioned'}});
  assert.equal(f.picker.selected(),false);assert.equal(f.$('model').value,beta.model);
  f.picker.configure({dream_one:beta});assert.equal(f.picker.selected(),true);
  f.picker.configure({});assert.equal(f.picker.selected(),false);
});
test('explicit runner selection survives model, robot and readiness changes',()=>{
  const f=fixture();f.picker.configure({dream_one:beta});f.choose('runner');
  f.picker.configure({dream_one:{...beta,available:false}});
  f.picker.configure({dream_one:beta,astra});
  f.$('provider').value='guest_astra';f.$('model').value=astra.model;f.refresh();
  assert.equal(f.$('executionLocation').value,'runner');
  assert.equal(f.picker.selected(),false);assert.deepEqual(f.picker.payload(),{});
  f.choose('auto');assert.equal(f.picker.payload().controller_model,'astra');
});
test('explicit controller mode starts with the matching model and rejects an unavailable retained choice',()=>{
  const f=fixture();f.picker.configure({astra,dream_one:beta});f.choose('controller');
  assert.equal(f.$('controllerModel').value,'dream_one');
  assert.equal(f.picker.payload().model,beta.model);
  f.picker.configure({astra,dream_one:{...beta,available:false,reason:'Unavailable here'}});
  assert.equal(f.$('controllerModel').value,'dream_one');
  assert.throws(()=>f.picker.payload(),/Unavailable here/);
});
test('explicit user endpoint and its entered model survive catalog refreshes and are never selected automatically',()=>{
  const f=fixture();f.picker.configure({astra,custom});
  f.choose('controller');f.$('controllerModel').value='custom';
  f.$('controllerEndpoint').value='https://example.com/v1/responses';f.$('controllerEndpointModel').value='user-model';
  f.picker.configure({astra:{...astra,available:false},custom});
  assert.equal(f.picker.payload().custom_endpoint.url,'https://example.com/v1/responses');
  assert.equal(f.picker.payload().model,'user-model');
  f.choose('auto');assert.equal(f.picker.selected(),false);
});
