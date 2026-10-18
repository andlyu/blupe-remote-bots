const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/hosted.js'),'utf8');
const fn=source.match(/  function providerChanged\([^]*?\n  }/)[0];
test('Reset bin keeps its fixed task/model and restores the previous model task',()=>{
 const nodes=new Map(),$=id=>{if(!nodes.has(id))nodes.set(id,{value:'',dataset:{},options:[],selectedOptions:[],close(){}});return nodes.get(id)};
 const context={$,configuredProviders:{reset_bin:{model:'reset-bin-v1',task:'Reset bin',help:'Replay then position.'}},window:{},selectedRobot:'fixture',aspireRunAvailable:false,aspireRetryLimit(){return 1},localStorage:{getItem(){return null}},setupProvider:null,updateRunLabel(){},updateSavedKey(){},claudeModel:'claude-opus-5-5'};
 const change=vm.runInNewContext('('+fn+')',context);
 $('prompt').value='Move a block';$('provider').value='reset_bin';change();
 assert.equal($('prompt').value,'Reset bin');assert.equal($('model').value,'reset-bin-v1');assert.equal($('prompt').readOnly,true);assert.equal($('apiKey').required,false);
 $('provider').value='codex';change();assert.equal($('prompt').value,'Move a block');assert.equal($('prompt').readOnly,false);
});
