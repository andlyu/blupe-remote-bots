const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/hosted.js'),'utf8');
const durationSource=source.split('function createProviderRunDuration(input) {')[1].split('\nfunction createRunVideoEmailControl')[0];
const providerBody=source.split('  function providerChanged(preview = true) {')[1].split('  if (window.createBlupeModelPicker) {')[0];
function page(initial='5') {
  const nodes={},listeners={};
  const $=id=>nodes[id]||={value:'',hidden:false,required:true,dataset:{},options:[],selectedOptions:[],close(){}};
  $('runDuration').value=initial;$('runDuration').defaultValue='5';
  $('runDuration').addEventListener=(name,fn)=>listeners[name]=fn;
  const context=vm.createContext({$,window:{},selectedRobot:'fixture',setupProvider:null,aspireRunAvailable:false,
    localStorage:{getItem(){return null}},aspireRetryLimit(){return 1},updateRunLabel(){},updateSavedKey(){},
    configuredProviders:{reset_bin:{model:'reset',task:'Reset bin',label:'Reset bin',default_run_duration_s:600},
      other_policy:{model:'other',task:'Other task',label:'Other policy'}}});
  const create=vm.runInContext('(function createProviderRunDuration(input){'+durationSource+')',context);
  context.window.yamRunDuration=create($('runDuration'));
  const changed=vm.runInContext('(function(){'+providerBody+')',context);
  const requestLine=source.split('\n').find(line=>line.includes('prompt: $(\'prompt\').value, run_duration_s:'));
  const requestDuration=requestLine.match(/run_duration_s:([^,]+)/)[1];
  return {select(provider){$('provider').value=provider;changed();},
    edit(value){$('runDuration').value=String(value);listeners.input();},
    minutes(){return $('runDuration').value;},
    requestSeconds(){return vm.runInContext(requestDuration,context);}};
}

test('actual provider selection sets Reset to ten minutes and the submit field to600seconds',()=>{
  const p=page();p.select('openai');assert.equal(p.minutes(),'5');assert.equal(p.requestSeconds(),300);
  p.select('reset_bin');assert.equal(p.minutes(),'10');assert.equal(p.requestSeconds(),600);
  p.select('other_policy');assert.equal(p.minutes(),'5');assert.equal(p.requestSeconds(),300);
  p.select('openai');assert.equal(p.minutes(),'5');
});

test('explicit Reset and other-provider choices survive same-provider refresh and switching',()=>{
  const p=page();p.select('openai');p.edit(8);
  p.select('reset_bin');assert.equal(p.minutes(),'10');p.edit(7);
  p.select('reset_bin');assert.equal(p.requestSeconds(),420);
  p.select('openai');assert.equal(p.requestSeconds(),480);
  p.select('reset_bin');assert.equal(p.minutes(),'7');assert.equal(p.requestSeconds(),420);
});

test('a browser-restored nondefault duration remains an explicit choice',()=>{
  const p=page('4');p.select('reset_bin');assert.equal(p.requestSeconds(),240);
  p.select('openai');assert.equal(p.requestSeconds(),300);
  p.select('reset_bin');assert.equal(p.requestSeconds(),240);
});
