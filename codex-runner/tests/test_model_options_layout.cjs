const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.env.YAM_TEST_HOSTED_JS || __dirname + '/../static/hosted.js', 'utf8');
const start = source.indexOf('  function positionModelOptions()');
const code = source.slice(start, source.indexOf('  window.yamShowModelOptions', start));

function harness({width=1280,height=720,anchorTop=620,anchorLeft=1000,contentHeight=370,visualViewport}={}) {
  let open=false, modelFocus=0, triggerFocus=0;
  const anchor={top:anchorTop,bottom:anchorTop+44,left:anchorLeft,width:160};
  const document={activeElement:null};
  const options={style:{},hidden:true,scrollHeight:contentHeight,scrollTop:90,
    matches:()=>open,contains:node=>node===model,
    showPopover(args){open=true;this.source=args?.source;},hidePopover(){open=false;},
    getBoundingClientRect(){return {width:Math.min(320,parseFloat(this.style.maxWidth)||width),height:Math.min(this.scrollHeight,parseFloat(this.style.maxHeight)||height),left:parseFloat(this.style.left)||0,top:parseFloat(this.style.top)||0};}};
  const settingsButton={getBoundingClientRect:()=>anchor,setAttribute(){},focus(){triggerFocus++;document.activeElement=this;}};
  const model={focus(){modelFocus++;document.activeElement=this;}};
  const window={innerWidth:width,innerHeight:height,visualViewport};
  const ctx={options,settingsButton,model,document,window};
  vm.runInNewContext(code+'\nthis.ui={positionModelOptions,showComposerOptions};',ctx);
  return {options,anchor,document,model,settingsButton,window,...ctx.ui,get modelFocus(){return modelFocus;},get triggerFocus(){return triggerFocus;}};
}
function assertBounds(h,{left=12,top=12,width=h.window.innerWidth-24,height=h.window.innerHeight-24}={}) {
  const r=h.options.getBoundingClientRect();
  assert(r.left>=left && r.top>=top,JSON.stringify(r));
  assert(r.left+r.width<=left+width+0.1,JSON.stringify(r));
  assert(r.top+r.height<=top+height+0.1,JSON.stringify(r));
  return r;
}
test('opening either or both disclosures preserves the bottom anchor and viewport bounds',()=>{
  const h=harness();
  for(const contentHeight of [370,720,1120,370]){
    h.options.scrollHeight=contentHeight;h.positionModelOptions();
    const r=assertBounds(h);assert.equal(r.top+r.height,h.anchor.top-8);
  }
});
test('a trigger near the top opens downward',()=>{
  const h=harness({anchorTop:30,anchorLeft:15});h.positionModelOptions();
  const r=assertBounds(h);assert.equal(r.top,h.anchor.bottom+8);
});
test('narrow short windows retain a usable scroll boundary without a forced minimum height',()=>{
  const h=harness({width:280,height:240,anchorTop:110,anchorLeft:10,contentHeight:1100});
  h.positionModelOptions();const r=assertBounds(h);assert(r.height<160);assert.equal(r.width,256);
});
test('an onscreen keyboard and visual viewport offset constrain the menu',()=>{
  const h=harness({width:390,height:844,anchorTop:480,anchorLeft:230,contentHeight:1100,
    visualViewport:{width:320,height:300,offsetLeft:35,offsetTop:220}});
  h.positionModelOptions();assertBounds(h,{left:47,top:232,width:296,height:276});
});
test('opening focuses the model once, reopening an already open menu preserves work',()=>{
  const h=harness();h.showComposerOptions(true);
  assert.equal(h.modelFocus,1);assert.equal(h.options.scrollTop,0);assert.equal(h.options.source,h.settingsButton);
  h.options.scrollTop=180;h.showComposerOptions(true);
  assert.equal(h.modelFocus,1);assert.equal(h.options.scrollTop,180);
});
test('closing returns focus to the trigger only when focus is inside',()=>{
  const h=harness();h.showComposerOptions(true);h.showComposerOptions(false);
  assert.equal(h.triggerFocus,1);assert.equal(h.options.hidden,true);
  h.showComposerOptions(true);h.document.activeElement={};h.showComposerOptions(false);
  assert.equal(h.triggerFocus,1);
});
test('invalid system prompt opens its own disclosure before browser validation',()=>{
  const start=source.indexOf('  function openRunIdentity()');
  const code=source.slice(start,source.indexOf('  send.addEventListener',start));
  const options={querySelectorAll:()=>[invalid]};
  const details={tagName:'DETAILS',open:false,parentElement:options};
  let reports=0;const invalid={parentElement:details,willValidate:true,validity:{valid:false},reportValidity(){assert(details.open);reports++;}};
  const nodes={openLocalRun:{disabled:false},prompt:{reportValidity:()=>true}};
  vm.runInNewContext(code+'\nopenRunIdentity();',{options,advanced:{contains:()=>false},$:id=>nodes[id],showComposerOptions(){}});
  assert.equal(reports,1);
});
