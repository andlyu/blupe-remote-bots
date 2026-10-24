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
      dream:{model:'dreamlabs/dream-1-beta',default_run_duration_s:120,max_run_duration_s:1200},
      dream_flash:{model:'dreamlabs/dream-1-flash',default_run_duration_s:120,max_run_duration_s:1200},
      other_policy:{model:'other',task:'Other task',label:'Other policy'}}});
  const create=vm.runInContext('(function createProviderRunDuration(input){'+durationSource+')',context);
  context.window.yamRunDuration=create($('runDuration'));
  const changed=vm.runInContext('(function(){'+providerBody+')',context);
  const requestLine=source.split('\n').find(line=>line.includes('prompt: $(\'prompt\').value, run_duration_s:'));
  const requestDuration=requestLine.match(/run_duration_s:([^,]+)/)[1];
  return {select(provider){$('provider').value=provider;changed();},
    edit(value){$('runDuration').value=String(value);listeners.input();},
    minutes(){return $('runDuration').value;},
    maximum(){return $('runDuration').max;},
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

for (const provider of ['dream','dream_flash']) {
  test(`${provider} accepts every minute through twenty and retains its two-minute default`,()=>{
    const p=page();p.select(provider);assert.equal(p.minutes(),'2');assert.equal(p.maximum(),'20');
    for(let minutes=1;minutes<=20;minutes++) {
      p.edit(minutes);p.select(provider);assert.equal(p.requestSeconds(),minutes*60);
    }
    p.edit(21);p.select(provider);assert.equal(p.requestSeconds(),1200);
    const restored=page('20');restored.select(provider);assert.equal(restored.requestSeconds(),1200);
  });
}

test('Dream choices stay independent and other providers retain ten-minute limits',()=>{
  const p=page('8');p.select('openai');assert.equal(p.requestSeconds(),480);
  p.select('dream');assert.equal(p.requestSeconds(),120);p.edit(20);
  p.select('dream_flash');assert.equal(p.requestSeconds(),120);assert.equal(p.maximum(),'20');
  p.edit(12);p.select('dream_flash');assert.equal(p.requestSeconds(),720);
  p.select('dream');assert.equal(p.requestSeconds(),1200);
  p.select('openai');assert.equal(p.requestSeconds(),480);assert.equal(p.maximum(),'10');
  p.edit(20);p.select('openai');assert.equal(p.requestSeconds(),600);
});
