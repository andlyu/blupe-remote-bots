const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/../static/camera-preview.js', 'utf8');

function harness(search = '') {
  let now = 200;
  const images = [], draws = [], listeners = {}, viewer = {dataset:{}};
  const tiles = ['top','observer','left','right'].map(role => {
    const label = {textContent:''};
    const figure = {dataset:{},querySelector:q=>q==='[data-sync-status]'?label:null};
    return {dataset:{cameraRole:role},setAttribute(){},closest:()=>figure,
      getContext:()=>({drawImage:(...args)=>draws.push({role,args})})};
  });
  const context = {location:{search,pathname:'/'},URLSearchParams,performance:{now:()=>now},
    requestAnimationFrame:fn=>fn(),Image:class {constructor(){images.push(this);this.naturalWidth=1280;this.naturalHeight=540;}async decode(){}},
    window:{addEventListener:(name,fn)=>listeners[name]=fn},document:{readyState:'complete',hidden:false,
      querySelectorAll:()=>tiles,getElementById:()=>viewer}};
  vm.runInNewContext(source,context);
  return {context,images,draws,tiles,viewer,listeners,time:v=>now=v};
}

test('cached composite paints before session setup and reuses the correct HD crops',async()=>{
  const h=harness();
  assert.equal(h.images[0].src,'/synchronized/preview.jpg?robot_id=yam-1');
  await h.images[0].onload();
  assert.equal(h.draws.length,4);
  assert.deepEqual(Array.from(h.draws.find(d=>d.role==='observer').args.slice(1)),[0,0,960,540,0,0,960,540]);
  assert(h.tiles.every(t=>t.dataset.frameSource==='preview'));
  assert.equal(h.viewer.dataset.firstCameraMs,'200.0');
});

test('a late preview cannot replace live video, a demand still, or another robot',async()=>{
  const h=harness();
  h.tiles[0].dataset.frameSource='video';h.tiles[1].dataset.frameSource='snapshot';
  await h.images[0].onload();assert.equal(h.draws.length,2);
  h.context.window.yamCameraPreview.paint('different',h.tiles);assert.equal(h.draws.length,2);
  h.time(5201);h.context.window.yamCameraPreview.paint('yam-1',h.tiles);assert.equal(h.draws.length,2);
  const switched=harness();switched.listeners['blupe-robot-selected']({detail:'robot-ba8413962083809c'});
  await switched.images[0].onload();assert.equal(switched.draws.length,0);
  assert.equal(switched.images[1].src,'/synchronized/preview.jpg?robot_id=robot-ba8413962083809c');
});

test('smaller startup stills keep the same observer and side-camera geometry',async()=>{
  const h=harness();h.images[0].naturalWidth=1024;h.images[0].naturalHeight=432;
  await h.images[0].onload();
  assert.deepEqual(Array.from(h.draws.find(d=>d.role==='observer').args.slice(1)),[0,0,768,432,0,0,768,432]);
  assert.deepEqual(Array.from(h.draws.find(d=>d.role==='top').args.slice(1)),[768,144,256,144,0,0,256,144]);
});

test('native HD preview shows the observer at full resolution before live startup',async()=>{
  const h=harness();h.images[0].naturalWidth=2560;h.images[0].naturalHeight=1080;
  await h.images[0].onload();
  assert.deepEqual(Array.from(h.draws.find(d=>d.role==='observer').args.slice(1)),[0,0,1920,1080,0,0,1920,1080]);
  assert.equal(h.tiles[1].width,1920);assert.equal(h.tiles[1].height,1080);
});

test('unrecognized robot and invalid image sizes leave normal startup available',async()=>{
  const h=harness('?robot_id=unadvertised');assert.equal(h.images.length,0);
  const invalid=harness();invalid.images[0].naturalWidth=640;await invalid.images[0].onload();
  assert.equal(invalid.draws.length,0);
});

test('Robo-house startup preview uses the same unpadded live camera crops',async()=>{
  const h=harness('?robot_id=robot-ba8413962083809c');
  h.images[0].naturalWidth=2560;h.images[0].naturalHeight=1080;
  await h.images[0].onload();
  assert.deepEqual(Array.from(h.draws.find(d=>d.role==='observer').args.slice(1)),[280,12,1360,1068,0,0,1360,1068]);
  assert.deepEqual(Array.from(h.draws.find(d=>d.role==='left').args.slice(1)),[2002,0,476,360,0,0,476,360]);
});
