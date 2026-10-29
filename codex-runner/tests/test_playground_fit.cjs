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
  const cameraHeight=parseFloat(h.values.get('--console-camera-height'));
  assert.equal(h.values.has('height'),false);
  assert.equal(h.values.get('--console-camera-width'),'1136px');
  assert.equal(h.viewer.dataset.detailLayout,'below');
  assert(cameraHeight>h.window.innerHeight,'large observer preserves its aspect ratio with lower thumbnails');
  for (const scroll of [500,2000,50000,0]) {
    h.window.scrollY=scroll;h.fit();
    assert.equal(parseFloat(h.values.get('--console-camera-height')),cameraHeight);
  }
});

test('an asynchronously displayed banner cannot change the desktop camera layout',()=>{
  const h=harness();h.workspace.documentTop=68;h.fit();
  const initial=h.values.get('--console-camera-height');
  h.workspace.documentTop+=118;h.fit();
  assert.equal(h.values.get('--console-camera-height'),initial);
  assert.equal(h.values.has('height'),false);
});

test('phone cameras remain above chat and discard desktop fixed sizing',()=>{
  const h=harness();h.fit();h.window.innerWidth=390;h.workspace.clientWidth=354;h.visuals.clientWidth=354;h.fit();
  assert.equal(h.values.has('height'),false);
  assert.equal(h.values.get('--console-camera-width'),'354px');
  assert.equal(h.viewer.dataset.detailLayout,'below');
  assert(parseFloat(h.values.get('--console-camera-height'))<300);
});
