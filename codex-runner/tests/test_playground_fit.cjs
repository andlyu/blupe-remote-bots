const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../static/hosted.js'),'utf8');
const fit = source.slice(source.indexOf('  function fitCameras()'),source.indexOf('  let cameraFitFrame = null;'));

function harness() {
  const values = new Map();
  const viewer={dataset:{layout:'observer-focus'}};
  const window={innerWidth:1440,innerHeight:650,scrollY:0};
  const workspace={clientWidth:1404,clientHeight:0,documentTop:200,
    getBoundingClientRect:()=>({top:workspace.documentTop-window.scrollY}),
    style:{setProperty:(name,value)=>values.set(name,value),removeProperty:name=>values.delete(name)},
  };
  Object.defineProperty(workspace.style,'height',{
    get:()=>values.get('height'),
    set:value=>{values.set('height',value);workspace.clientHeight=parseFloat(value);},
  });
  const context={window,workspace,visuals:{clientWidth:1136},
    $:id=>id==='liveViewer' ? viewer : {offsetHeight:21},
    document:{querySelector:()=>({offsetHeight:24}),getElementById:()=>({offsetHeight:56})},
  };
  vm.runInNewContext(fit+'\nthis.fit=fitCameras;',context);
  return {window,workspace,viewer,values,visuals:context.visuals,fit:context.fit};
}

test('desktop camera column keeps its full width and scrolling cannot inflate it',()=>{
  const h=harness();h.fit();
  const viewportHeight=parseFloat(h.values.get('--console-viewport-height'));
  assert.equal(h.values.has('height'),false);
  assert.equal(h.values.get('--console-camera-width'),'1136px');
  assert.equal(h.viewer.dataset.detailLayout,'side');
  assert.equal(h.workspace.documentTop+viewportHeight+16,h.window.innerHeight,'workspace and footer fit above the bottom screen edge');
  for (const scroll of [500,2000,50000,0]) {
    h.window.scrollY=scroll;h.fit();
    assert.equal(parseFloat(h.values.get('--console-viewport-height')),viewportHeight);
  }
});

test('a banner reduces the height budget while keeping the desktop side column',()=>{
  const h=harness();h.workspace.documentTop=68;h.fit();
  const initial=parseFloat(h.values.get('--console-viewport-height'));
  h.workspace.documentTop+=118;h.fit();
  assert.equal(parseFloat(h.values.get('--console-viewport-height')),initial-118);
  assert.equal(h.viewer.dataset.detailLayout,'side');
  assert.equal(h.values.has('height'),false);
});

test('phone cameras remain above chat and discard desktop fixed sizing',()=>{
  const h=harness();h.fit();h.window.innerWidth=390;h.workspace.clientWidth=354;h.visuals.clientWidth=354;h.fit();
  assert.equal(h.values.has('height'),false);
  assert.equal(h.values.get('--console-camera-width'),'354px');
  assert.equal(h.viewer.dataset.detailLayout,'below');
  assert(parseFloat(h.values.get('--console-camera-height'))<300);
});

test('common desktop heights keep the complete workspace inside the viewport',()=>{
  const h=harness();h.workspace.documentTop=92;
  for(const height of [500,650,768,868,1080]){
    h.window.innerHeight=height;h.fit();
    assert.equal(parseFloat(h.values.get('--console-viewport-height'))+92+16,height);
    assert.equal(h.values.get('--console-camera-width'),'1136px');
    assert.equal(h.viewer.dataset.detailLayout,'side');
  }
});
