const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/hosted.js'), 'utf8');
const body = source.split('  function providerChanged(preview = true) {')[1].split('  if (window.createBlupeModelPicker) {')[0];

test('configured policy clears stale credentials and subscription state but keeps the task', () => {
  const nodes = {};
  const $ = id => nodes[id] ||= {value: '', hidden: false, required: true, dataset: {}, options: [], selectedOptions: [], close() {}};
  $('provider').value = 'molmoact';
  $('apiKey').value = 'stale-key';
  $('prompt').value = 'Put blue block in bin.';
  $('prompt').readOnly = true;
  const changed = vm.runInNewContext('(function(){' + body + ')', {
    $ , window:{}, selectedRobot:'fixture',localStorage:{getItem(){return null}},aspireRetryLimit(){return 1}, setupProvider: 'codex', aspireRunAvailable:false, updateRunLabel() {},
    configuredProviders: {molmoact: {model: 'test-abc', label: 'ABC MolmoAct', help: 'Pinned policy'}}
  });
  changed();
  assert.equal($('model').value, 'test-abc');
  assert.equal($('apiKey').value, '');
  assert.equal($('apiKey').required, false);
  assert.equal($('prompt').value, 'Put blue block in bin.');
  assert.equal($('prompt').readOnly, false);
  for (const id of ['providerFields', 'codexSetup', 'claudeSetup', 'apiDepthSettings', 'speedField', 'effortField']) {
    assert.equal($(id).hidden, true, id);
  }
});

test('Gemini mode is visible only for Gemini and changing provider preserves selected mode', () => {
  const nodes = {};
  const $ = id => nodes[id] ||= {value:'',hidden:false,dataset:{},options:[],selectedOptions:[],close(){}};
  const changed = vm.runInNewContext('(function(){' + body + ')', {
    $, window:{}, selectedRobot:'fixture', localStorage:{getItem(){return null}}, aspireRetryLimit(){return 1},
    setupProvider:null, aspireRunAvailable:false, updateRunLabel(){}, updateSavedKey(){}, claudeModel:'claude-opus-5-5',
    configuredProviders:{gemini:{model:'gemini-4-argon',label:'Gemini 4 Argon'}}
  });
  $('provider').value='gemini'; $('geminiCallingMode').value='normal'; changed();
  assert.equal($('geminiCallingModeField').hidden,false);
  assert.equal($('geminiCallingMode').value,'normal');
  assert.equal($('responseSpeed').value,'standard');
  assert.equal($('model').value,'gemini-4-argon');
  for (const provider of ['openai','codex','anthropic','claude']) {
    $('provider').value=provider;changed();
    assert.equal($('geminiCallingModeField').hidden,true);
    assert.equal($('geminiCallingMode').value,'normal');
  }
});

test('submitted Gemini mode is scoped to Gemini and is disabled during active runs', () => {
  const statement = source.split('\n').find(line => line.includes('payload.gemini_calling_mode ='));
  for (const provider of ['gemini','guest_gemini','openai','claude','guest_astra']) {
    const payload={provider};
    vm.runInNewContext(statement, {payload, $:()=>({value:'normal'})});
    assert.equal(payload.gemini_calling_mode,['gemini','guest_gemini'].includes(provider)?'normal':undefined);
  }
  const buttons=source.split('  function buttons() {')[1].split('  let savedKeyProviders')[0];
  const nodes={};const $=id=>nodes[id]||={};
  const update=vm.runInNewContext('(function(){'+buttons+')', {$,csrf:'test',ended:false,active:true,submitting:false,
    ownRunLive:false,conversationSharingAllowed:true,updateRunLabel(){}});
  update(); assert.equal($('geminiCallingMode').disabled,true);
});
