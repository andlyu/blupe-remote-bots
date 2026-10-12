const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.env.YAM_TEST_HOSTED_JS || __dirname+'/../static/hosted.js','utf8');
const start=source.indexOf("  send.addEventListener('click', () => {");
const handler=source.slice(start,source.indexOf('  const prompt =',start));
function harness({active=false,queued=false}={}) {
  const clicks=[],nodes={};let click;
  for(const id of ['run','stop','leaveQueue','openLocalRun'])nodes[id]={click:()=>clicks.push(id)};
  nodes.leaveQueue.hidden=!queued;nodes.leaveQueue.disabled=!queued;
  nodes.runForm={classList:{contains:()=>active}};
  vm.runInNewContext(handler,{openRunIdentity:()=>clicks.push('identity'),$:id=>nodes[id],send:{addEventListener:(_,fn)=>{click=fn;}}});
  click();return clicks;
}
test('idle task opens identity confirmation before submission',()=>{
  assert.deepEqual(harness(),['identity']);
});
test('active task and queue preserve their respective stop handlers',()=>{
  assert.deepEqual(harness({active:true}),['stop']);
  assert.deepEqual(harness({active:true,queued:true}),['leaveQueue']);
});
const setupStart=source.indexOf('  function openRunIdentity()');
const setup=source.slice(setupStart,source.indexOf("  send.addEventListener",setupStart));
for(const mode of ['missing','present','disabled','invalid'])test('identity confirmation with '+mode+' launch state',()=>{
  let existing=0,opened=0,focused=0,reported=0;const popover=[];
  const dialog={open:false,showModal(){this.open=true;opened++;}};
  const launch={disabled:mode==='disabled',click(){existing++;if(mode==='present')dialog.open=true;}};
  const invalid={willValidate:true,validity:{valid:false},reportValidity(){reported++;}};
  const advanced={open:false,contains:()=>true};
  const nodes={openLocalRun:launch,localRunDialog:dialog,runSettings:{},prompt:{reportValidity:()=>true},runnerName:{focus(){focused++;}}};
  vm.runInNewContext(setup+'\nopenRunIdentity();',{$:id=>nodes[id],advanced,
    options:{querySelectorAll:()=>mode==='invalid'?[invalid]:[]},showComposerOptions:open=>popover.push(open)});
  assert.equal(existing,['disabled','invalid'].includes(mode)?0:1);
  assert.equal(dialog.open,!['disabled','invalid'].includes(mode));
  assert.equal(opened,mode==='missing'?1:0);
  assert.equal(focused,['disabled','invalid'].includes(mode)?0:1);
  if(mode==='invalid'){assert.equal(advanced.open,true);assert.equal(reported,1);assert.deepEqual(popover,[true]);}
});
