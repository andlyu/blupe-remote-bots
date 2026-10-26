const assert=require('node:assert/strict');
const {test}=require('node:test');
const {spawnSync}=require('node:child_process');
const path=require('node:path');
const C=require('../static/path-studio-core.js');

test('browser FK matches an independently loaded canonical MuJoCo XML chain',()=>{
  const script=String.raw`
import json, math, xml.etree.ElementTree as ET, sys
root=ET.parse(sys.argv[1]).getroot()
def mul(a,b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def tf(body):
    w,x,y,z=map(float,body.get('quat','1 0 0 0').split()); n=math.sqrt(w*w+x*x+y*y+z*z); w,x,y,z=[v/n for v in (w,x,y,z)]
    px,py,pz=map(float,body.get('pos','0 0 0').split())
    return [[1-2*y*y-2*z*z,2*x*y-2*w*z,2*x*z+2*w*y,px],[2*x*y+2*w*z,1-2*x*x-2*z*z,2*y*z-2*w*x,py],[2*x*z-2*w*y,2*y*z+2*w*x,1-2*x*x-2*y*y,pz],[0,0,0,1]]
poses=[[0,0,0,0,0,0],[0,1,1.2,0,0,0],[.4,1.5,.8,-.2,.3,.5],[-.6,.7,2,.3,-.4,-.5]]
out=[]
for q in poses:
    m=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]
    body=root.find("./worldbody/body[@name='left_link1']")
    for angle in q:
        m=mul(m,tf(body)); joint=body.find('joint'); sign=float(joint.get('axis').split()[2]); c=math.cos(angle*sign); s=math.sin(angle*sign)
        m=mul(m,[[c,-s,0,0],[s,c,0,0],[0,0,1,0],[0,0,0,1]]); body=body.find('body')
    m=mul(m,tf(body)); out.append({'q':q,'p':[m[0][3],m[1][3]-.35,m[2][3]]})
print(json.dumps(out))
`;
  const result=spawnSync('python3',['-c',script,path.resolve(__dirname,'../models/yam_bimanual/yam_bimanual.xml')],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  for(const {q,p} of JSON.parse(result.stdout))assert.ok(C.distance(C.forward(q).position,p)<1e-7,JSON.stringify({q,p,actual:C.forward(q).position}));
});

test('representative spatial paths solve continuously within model joint limits',()=>{
  const paths=[
    Array.from({length:25},(_,i)=>{const t=i/24;return [.23+.19*t,-.14+.28*t,.28+.055*Math.sin(t*Math.PI*2)];}),
    Array.from({length:19},(_,i)=>{const t=i/18;return [.30,-.14+.28*t,.24+.15*Math.sin(t*Math.PI)];}),
    [[.24,-.12,.28],[.4,-.12,.28],[.4,.12,.28],[.24,.12,.28],[.24,-.12,.28]]
  ];
  for(const points of paths){const plan=C.samplePath(points);let seed=null;
    for(const sample of plan.samples){const solved=seed?C.inverse(sample.position,seed,80):C.solve(sample.position);
      assert.ok(solved.reachable,`Unreachable ${sample.position}`);assert.ok(C.distance(sample.position,C.forward(solved.joints).position)<.0015);
      solved.joints.forEach((q,i)=>{assert.ok(q>=C.frames[i].limit[0]&&q<=C.frames[i].limit[1]);if(seed)assert.ok(Math.abs(q-seed[i])<.35);});
      sample.joints=solved.joints;seed=solved.joints;
    }
    for(let d=0;d<plan.total;d+=.002){const sample=C.atDistance(plan.samples,d);assert.ok(C.distance(sample.position,C.forward(sample.joints).position)<.0015,'Joint interpolation must track Cartesian interpolation');}
  }
});

test('unreachable targets are reported rather than clamped to a fake tool position',()=>{
  const target=[.75,.75,.75],solved=C.solve(target);assert.equal(solved.reachable,false);assert.ok(solved.error>.1);
  assert.ok(C.distance(C.forward(solved.joints).position,target)>.1);
});

test('arc-length sampling preserves corners, skips duplicate points, and includes exact endpoints',()=>{
  const points=[[.2,0,.3],[.2,0,.3],[.3,0,.3],[.3,.1,.3]],plan=C.samplePath(points);
  assert.ok(Math.abs(plan.total-.2)<1e-9);assert.deepEqual(plan.samples[0].position,points[0]);assert.deepEqual(plan.samples.at(-1).position,points.at(-1));
  for(let i=1;i<plan.samples.length;i++){assert.ok(plan.samples[i].distance>plan.samples[i-1].distance);assert.ok(C.distance(plan.samples[i].position,plan.samples[i-1].position)<=.005001);}
  assert.ok(C.distance(C.atDistance(plan.samples,.15).position,[.3,.05,.3])<1e-9);
  assert.throws(()=>C.samplePath([[.2,0,.3],[.2,0,.3]]),/1 mm/);
});

test('JSON rejects frame/unit mismatches, nonfinite values, bounds, excessive size and malformed points',()=>{
  const points=[[.3,0,.3],[.4,.1,.3]],envelope={schema:'blupe.cartesian-path.v1',units:'m',frame:'yam_left_base',points};
  assert.deepEqual(C.parsePath(envelope),points.map(p=>C.armWorld(p,'left')));assert.deepEqual(C.parsePath(points),points);
  assert.deepEqual(C.parsePath({schema:'blupe.bimanual-path.v1',units:'m',frame:'yam_common',points}),points);
  for(const invalid of [{...envelope,units:'mm'},{...envelope,frame:'world'},null,[[.3,0]],[[.3,0,NaN],[.4,0,.3]],[[.3,0,.001],[.4,0,.3]],[[9,0,.3],[.4,0,.3]],[['.3',0,.3],[.4,0,.3]],Array(2001).fill(points[0])])assert.throws(()=>C.parsePath(invalid));
  assert.throws(()=>C.samplePath(Array.from({length:2000},(_,i)=>[i%2?.7:-.7,0,.3])),/too long/);
});

test('shape prompts produce closed, continuous, reachable outlines including a recognizable heart',()=>{
  for(const name of ['heart','star','circle','square','triangle','infinity']){
    const shape=C.fromPrompt(`Please draw a ${name}`);assert.equal(shape.name,name);assert.deepEqual(shape.points[0],shape.points.at(-1));
    for(const [side,path] of Object.entries(C.assignPath(shape.points,'both'))) {
      const plan=C.samplePath(path);let seed;
      for(const s of plan.samples){const target=C.armLocal(s.position,side),result=seed?C.inverse(target,seed,80):C.solve(target);assert.ok(result.reachable,`${name} ${side}: ${s.position}`);if(seed)assert.ok(result.joints.every((v,i)=>Math.abs(v-seed[i])<.35));seed=result.joints;s.joints=result.joints;}
      for(let d=0;d<plan.total;d+=.002){const s=C.atDistance(plan.samples,d),world=C.armWorld(C.forward(s.joints).position,side);assert.ok(C.distance(s.position,world)<.0015,`${name} ${side} interpolation`);}
    }
  }
  const heart=C.fromPrompt('draw a heart').points;
  // Top indentation, two lobes, and the low central point characterize the outline.
  assert.ok(heart[12][2]>heart[0][2]);assert.ok(heart[84][2]>heart[0][2]);assert.ok(heart[48][2]<heart[0][2]-.1);
  assert.equal(C.fromPrompt('♥').name,'heart');assert.equal(C.fromPrompt('draw a figure-eight').name,'infinity');
  for(const text of ['','draw a dinosaur','draw a heart and a star'])assert.throws(()=>C.fromPrompt(text));
});

test('bimanual assignment covers the full polyline once and both arms meet at the arc midpoint',()=>{
  const shapes=[C.fromPrompt('draw a heart').points,[[.34,-.2,.3],[.34,.1,.4],[.34,.25,.25]],[[.34,.1,.3],[.34,.1,.3],[.34,-.1,.3]],[[.34,-.1,.3],[.34,.1,.3]]];
  for(const points of shapes){
    const full=C.samplePath(points),assigned=C.assignPath(points),left=C.samplePath(assigned.left),right=C.samplePath(assigned.right);
    assert.ok(Math.abs(left.total+right.total-full.total)<1e-8);assert.ok(Math.abs(left.total-right.total)<1e-8);
    assert.ok(C.distance(assigned.left.at(-1),assigned.right.at(-1))<1e-9);
    assert.ok(C.distance(assigned.left.at(-1),C.atDistance(full.samples,full.total/2).position)<1e-9);
  }
  const p=[.34,.12,.3];assert.deepEqual(C.armWorld(C.armLocal(p,'left'),'left'),p);assert.ok(C.distance(C.armWorld(C.armLocal(p,'right'),'right'),p)<1e-10);
  assert.equal(C.BASES.left[1]-C.BASES.right[1],.6);
  const heart=C.assignPath(C.fromPrompt('heart').points),lp=heart.left[20],rp=heart.right[20];
  assert.ok(lp[1]>0&&rp[1]<0);const l=C.solve(C.armLocal(lp,'left')),r=C.solve(C.armLocal(rp,'right'));assert.notDeepEqual(l.joints,r.joints,'Two independent IK solutions are required');
  assert.deepEqual(Object.keys(C.assignPath(shapes[0],'left')),['left']);assert.deepEqual(Object.keys(C.assignPath(shapes[0],'right')),['right']);
});

test('controller mesh provenance and URDF-derived frames are retained',()=>{
  const fs=require('node:fs'),crypto=require('node:crypto'),model=require('../static/path-studio-yam-model.js');
  assert.equal(model.provenance.controller_commit,'d1f9e8d588b18810d13c0edbe34646763dc8f257');
  assert.equal(model.visuals.length,9);assert.equal(Object.keys(model.meshes).length,9);
  for(const [relative,hash] of Object.entries(model.provenance.hashes))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.resolve(__dirname,'..',relative))).digest('hex'),hash,relative);
  for(const [name,encoded] of Object.entries(model.meshes)){const bytes=Buffer.from(encoded,'base64');assert.equal(bytes.length,84+bytes.readUInt32LE(80)*50,`${name} valid binary STL`);}
});

test('Robo-house is 60 cm and YAM1 is 50 cm in both rendering bases and IK coordinates',()=>{
  try {
    for(const [station,spacing] of [['robohouse',.60],['yam-1',.50]]) {
      C.setStation(station);assert.equal(C.getStation(),station);assert.equal(C.BASES.left[1]-C.BASES.right[1],spacing);
      const paths=C.assignPath(C.fromPrompt('heart').points);
      for(const [side,points] of Object.entries(paths)){let q;
        for(const sample of C.samplePath(points).samples){const target=C.armLocal(sample.position,side),solved=q?C.inverse(target,q,80):C.solve(target);assert.ok(solved.reachable,`${station} ${side}`);assert.ok(C.distance(C.armWorld(C.forward(solved.joints).position,side),sample.position)<.0015);q=solved.joints;}
      }
    }
    assert.throws(()=>C.setStation('unknown'));
  }finally {C.setStation('robohouse');}
});

test('real drawing traces discard approach, retraction, inter-arm jumps and sparse chords',()=>{
  const path=[[.3,0,.2],[.3,0,.3],[.3,.1,.3]];
  const start=C.drawingTrace(null,[.3,0,.2],path,'left',1);assert.equal(start.segment,null);
  const draw=C.drawingTrace(start.last,[.3,0,.25],path,'left',1.5);assert.ok(draw.segment);
  const travel=C.drawingTrace(draw.last,[.1,-.3,.1],path,null,2);assert.equal(travel.last,null);assert.equal(travel.segment,null);
  const reenter=C.drawingTrace(travel.last,[.3,.1,.3],path,'left',2.5);assert.equal(reenter.segment,null);
  assert.equal(C.drawingTrace(start.last,[.3,.1,.3],path,'left',1.5).segment,null,'diagonal must not cut the corner');
  assert.equal(C.drawingTrace(draw.last,[.3,0,.26],path,'right',2).segment,null,'arm change breaks continuity');
  assert.equal(C.drawingTrace(draw.last,[.3,0,.26],path,'left',8).segment,null,'stale gap breaks continuity');
});

test('approximate execution shows the actual measured stroke within its allowed deviation',()=>{
  const path=[[.3,0,.2],[.3,0,.3]],a=[.3,.014,.2],b=[.3,.014,.25];
  assert.equal(C.drawingTrace(null,a,path,'left',1).last,null);
  const first=C.drawingTrace(null,a,path,'left',1,.03);
  const next=C.drawingTrace(first.last,b,path,'left',1.5,.03);
  assert.deepEqual(next.segment,[a,b]);
  assert.equal(C.drawingTrace(next.last,[.3,.04,.28],path,'left',2,.03).last,null);
});

test('gripper visual uses original slide range with normalized measured opening',()=>{
  const model=require('../static/path-studio-yam-model.js'),fingers=model.visuals.filter(v=>v.slide);
  assert.equal(fingers.length,2);
  for(const spec of fingers){const closed=C.visualTransform(spec,0),open=C.visualTransform(spec,1),half=C.visualTransform(spec,.5);
    assert.ok(Math.abs(Math.hypot(...[3,7,11].map(k=>open[k]-closed[k]))-.0475)<1e-8);
    for(const k of [3,7,11])assert.ok(Math.abs(half[k]-(closed[k]+open[k])/2)<1e-8);
  }
});

test('observer crop follows the real synchronized stream layout',()=>{
  assert.deepEqual(C.observerRect(2560,1080,'robohouse'),[0,0,1920,1080]);
  assert.deepEqual(C.observerRect(1280,720,'robohouse'),[640,360,640,360]);
  assert.deepEqual(C.observerRect(1280,720,'yam-1'),[640,0,640,360]);
});
