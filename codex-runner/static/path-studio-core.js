/* Position-only kinematics derived from the controller YAM URDF. Metres, radians, Z up.
 * These routines are a visual preview, not the hardware motion guard. */
(function (root) {
  'use strict';
  const model=typeof module!=='undefined'&&module.exports?require('./path-studio-yam-model.js'):root.PathStudioYamModel;
  if(!model)throw Error('The controller YAM model did not load. Refresh the local workspace.');
  const frames=model.frames;
  const identity=()=>[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  function multiply(a,b) {
    const m=Array(16).fill(0);
    for(let r=0;r<4;r++) for(let c=0;c<4;c++) for(let k=0;k<4;k++) m[r*4+c]+=a[r*4+k]*b[k*4+c];
    return m;
  }
  function transform(p,q) {
    const n=Math.hypot(...q),[w,x,y,z]=q.map(v=>v/n);
    return [1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w),p[0],2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w),p[1],2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y),p[2],0,0,0,1];
  }
  const origins=frames.map(f=>transform(f.p,f.q));
  const position=m=>[m[3],m[7],m[11]];
  const distance=(a,b)=>Math.hypot(...a.map((v,i)=>v-b[i]));
  function visualTransform(spec,gripper=0) {
    let m=identity();
    spec.transforms.forEach((t,i)=>{
      let p=t.p;
      if(spec.slide?.transform_index===i) {
        const g=Math.max(0,Math.min(1,gripper)),s=spec.slide;
        p=p.map((v,k)=>v+s.axis[k]*(s.range[0]+g*(s.range[1]-s.range[0])));
      }
      m=multiply(m,transform(p,t.q));
    });return m;
  }
  function pathDistance(p,path) {
    let best=Infinity;
    for(let i=1;i<path.length;i++) {
      const a=path[i-1],d=path[i].map((v,k)=>v-a[k]),den=d.reduce((s,v)=>s+v*v,0);
      const t=den?Math.max(0,Math.min(1,d.reduce((s,v,k)=>s+v*(p[k]-a[k]),0)/den)):0;
      best=Math.min(best,distance(p,a.map((v,k)=>v+t*d[k])));
    }return best;
  }
  function drawingTrace(previous,point,path,stroke,observedAt,tolerance=.006) {
    if(!stroke||!Number.isFinite(observedAt)||pathDistance(point,path)>tolerance)return {last:null,segment:null};
    const last={point:point.slice(),stroke,observedAt};
    if(!previous||previous.stroke!==stroke||observedAt<=previous.observedAt||observedAt-previous.observedAt>2)return {last,segment:null};
    const length=distance(previous.point,point),count=Math.max(1,Math.ceil(length/.003));
    // A sparse measurement chord must not cut across the drawing or connect
    // a retracted tool to the last stroke. Keep the planned outline visible.
    if(length<.001||length>.20)return {last,segment:null};
    for(let i=0;i<=count;i++)if(pathDistance(point.map((v,k)=>previous.point[k]+(v-previous.point[k])*i/count),path)>tolerance)return {last,segment:null};
    return {last,segment:[previous.point,point]};
  }
  function observerRect(width,height,station) {
    if(width===2560&&height===1080)return [0,0,1920,1080];
    return station==='robohouse'?[width/2,height/2,width/2,height/2]:[width/2,0,width/2,height/2];
  }
  function forward(joints) {
    let m=identity();
    const points=[[0,0,0]],axes=[],matrices=[];
    frames.forEach((f,i)=>{
      m=multiply(m,origins[i]);points.push(position(m));
      const sign=f.sign||1;axes.push([m[2]*sign,m[6]*sign,m[10]*sign]);
      const a=joints[i]*sign,c=Math.cos(a),s=Math.sin(a);
      m=multiply(m,[c,-s,0,0,s,c,0,0,0,0,1,0,0,0,0,1]);matrices.push(m);
    });
    const tool=multiply(m,transform(model.tool.p,model.tool.q));
    points.push(position(tool));
    return {points,axes,matrices,tool,position:position(tool)};
  }
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  function solve3(a,b) {
    const m=a.map((r,i)=>[...r,b[i]]);
    for(let c=0;c<3;c++) {
      let best=c;for(let r=c+1;r<3;r++) if(Math.abs(m[r][c])>Math.abs(m[best][c])) best=r;
      [m[c],m[best]]=[m[best],m[c]];
      if(Math.abs(m[c][c])<1e-12) return [0,0,0];
      const d=m[c][c];for(let k=c;k<4;k++) m[c][k]/=d;
      for(let r=0;r<3;r++) if(r!==c) {const f=m[r][c];for(let k=c;k<4;k++) m[r][k]-=f*m[c][k];}
    }
    return m.map(r=>r[3]);
  }
  const HOME=[0,1.0,1.2,0,0,0];
  const STATIONS={robohouse:{name:'Robo-house YAM',spacing:.60},'yam-1':{name:'YAM1',spacing:.50}};
  let station='robohouse';
  const BASES={left:[0,.30,0],right:[0,-.30,0]};
  function setStation(id) {
    if(!Object.hasOwn(STATIONS,id))throw Error('Choose Robo-house or YAM1.');
    station=id;BASES.left[1]=STATIONS[id].spacing/2;BASES.right[1]=-STATIONS[id].spacing/2;return STATIONS[id];
  }
  const armLocal=(point,side)=>point.map((v,i)=>v-BASES[side][i]);
  const armWorld=(point,side)=>point.map((v,i)=>v+BASES[side][i]);
  function inverse(target,seed=HOME,maxIterations=100) {
    const q=seed.slice();let error=Infinity;
    for(let n=0;n<maxIterations;n++) {
      const fk=forward(q),delta=target.map((v,i)=>v-fk.position[i]);error=Math.hypot(...delta);
      if(error<.0004) return {joints:q,error,reachable:true};
      const j=fk.axes.map((axis,i)=>cross(axis,fk.position.map((v,k)=>v-fk.points[i+1][k])));
      const a=Array.from({length:3},(_,r)=>Array.from({length:3},(_,c)=>j.reduce((s,col)=>s+col[r]*col[c],r===c?.00015:0)));
      const d=solve3(a,delta);
      q.forEach((v,i)=>{const step=j[i].reduce((s,v,k)=>s+v*d[k],0);q[i]=Math.max(frames[i].limit[0],Math.min(frames[i].limit[1],v+Math.max(-.15,Math.min(.15,step))));});
    }
    error=distance(target,forward(q).position);
    return {joints:q,error,reachable:error<.0015};
  }
  function solve(target,seed=HOME) {
    let best=inverse(target,seed);
    if(best.reachable) return best;
    for(const q of [HOME,[.6,1.6,1.8,0,.2,0],[-.6,.6,1.8,0,-.2,0],[0,2.5,2,0,0,0]]) {
      const next=inverse(target,q,160);if(next.error<best.error) best=next;if(best.reachable) break;
    }
    return best;
  }
  function validatePoints(points) {
    if(!Array.isArray(points)||points.length<2||points.length>2000) throw Error('Use between 2 and 2,000 XYZ points.');
    return points.map((p,i)=>{
      if(!Array.isArray(p)||p.length!==3||!p.every(v=>typeof v==='number'&&Number.isFinite(v))) throw Error(`Point ${i+1} needs three finite numbers.`);
      if(p.some(v=>Math.abs(v)>.8)||p[2]<.02) throw Error(`Point ${i+1} is outside the preview bounds (±0.8 m, Z ≥ 0.02 m).`);
      return p.slice();
    });
  }
  function parsePath(value) {
    let points=value;
    if(!Array.isArray(value)) {
      if(!value||value.units!=='m'||!(value.schema==='blupe.cartesian-path.v1'&&value.frame==='yam_left_base'||value.schema==='blupe.bimanual-path.v1'&&value.frame==='yam_common')) throw Error('Expected a Path Studio export in metres, or an array of common-frame XYZ triples.');
      points=value.points;
      if(value.frame==='yam_left_base') return validatePoints(points).map(p=>armWorld(p,'left'));
    }
    return validatePoints(points);
  }
  function samplePath(points,spacing=.005) {
    validatePoints(points);
    const samples=[{position:points[0].slice(),distance:0}],cumulative=[0];let total=0;
    for(let i=1;i<points.length;i++) {
      const len=distance(points[i-1],points[i]),count=Math.ceil(len/spacing);
      if(samples.length+count>5000) throw Error('Path is too long or dense. Use at most 5,000 preview samples.');
      for(let n=1;n<=count;n++) samples.push({position:points[i-1].map((v,k)=>v+(points[i][k]-v)*n/count),distance:total+len*n/count});
      total+=len;cumulative.push(total);
    }
    if(total<.001) throw Error('Draw a path at least 1 mm long.');
    return {samples,total,cumulative};
  }
  function atDistance(samples,d) {
    if(d<=0) return samples[0];if(d>=samples.at(-1).distance) return samples.at(-1);
    let lo=0,hi=samples.length-1;
    while(hi-lo>1) {const mid=(lo+hi)>>1;if(samples[mid].distance<d) lo=mid;else hi=mid;}
    const a=samples[lo],b=samples[hi],t=(d-a.distance)/(b.distance-a.distance);
    return {position:a.position.map((v,i)=>v+(b.position[i]-v)*t),joints:a.joints?.map((v,i)=>v+(b.joints[i]-v)*t),distance:d};
  }
  // A small, explicit shape vocabulary works offline without a model or key.
  function fromPrompt(prompt) {
    if(typeof prompt!=='string'||!prompt.trim())throw Error('Enter a shape, for example: draw a heart.');
    const names=[['heart',/\bheart\b|[❤♥]/i],['circle',/\bcircle\b/i],['star',/\bstar\b/i],['square',/\bsquare\b/i],['triangle',/\btriangle\b/i],['infinity',/\binfinity\b|\bfigure[ -]?eight\b|∞/i]];
    const matches=names.filter(([,pattern])=>pattern.test(prompt));
    if(matches.length!==1)throw Error(matches.length?'Choose one shape at a time.':'Try “draw a heart”, circle, star, square, triangle, or infinity.');
    const name=matches[0][0];let outline;
    const loop=(fn,n=96)=>Array.from({length:n+1},(_,i)=>fn(i/n*Math.PI*2));
    if(name==='heart')outline=loop(t=>[.0075*16*Math.sin(t)**3,.0075*(13*Math.cos(t)-5*Math.cos(2*t)-2*Math.cos(3*t)-Math.cos(4*t))]);
    if(name==='circle')outline=loop(t=>[.115*Math.sin(t),.115*Math.cos(t)]);
    if(name==='star')outline=Array.from({length:11},(_,i)=>{const t=i*Math.PI/5,r=i%2?.052:.12;return [r*Math.sin(t),r*Math.cos(t)];});
    if(name==='square')outline=[[-.105,.105],[.105,.105],[.105,-.105],[-.105,-.105],[-.105,.105]];
    if(name==='triangle')outline=[[0,.12],[.12,-.1],[-.12,-.1],[0,.12]];
    if(name==='infinity')outline=loop(t=>[.14*Math.cos(t)/(1+Math.sin(t)**2),.14*Math.cos(t)*Math.sin(t)/(1+Math.sin(t)**2)]);
    const points=outline.map(([y,z])=>[.34,y,.31+z]);
    // Close numerically so the simulated tool finishes at exactly the start.
    points[points.length-1]=points[0].slice();return {name,points};
  }
  function assignPath(points,assignment='both') {
    const full=samplePath(points);
    if(assignment==='left'||assignment==='right')return {[assignment]:points.map(p=>p.slice())};
    if(assignment!=='both')throw Error('Choose both arms, left arm, or right arm.');
    if(full.total<.002)throw Error('Draw a path at least 2 mm long for both arms.');
    const half=full.total/2,mid=atDistance(full.samples,half).position;
    const first=[points[0]],second=[mid];
    for(let i=1;i<points.length;i++) {
      if(full.cumulative[i]<half-1e-9)first.push(points[i]);
      else if(full.cumulative[i]>half+1e-9)second.push(points[i]);
    }
    first.push(mid);
    // The second arm starts at the opposite end and meets the first at halfway.
    if(distance(second.at(-1),points.at(-1))>1e-9)second.push(points.at(-1));
    second.reverse();
    const averageY=path=>path.reduce((s,p)=>s+p[1],0)/path.length;
    return averageY(first)>=averageY(second)?{left:first,right:second}:{left:second,right:first};
  }
  const api={frames,HOME,BASES,STATIONS,setStation,getStation:()=>station,armLocal,armWorld,forward,inverse,solve,distance,parsePath,validatePoints,samplePath,atDistance,fromPrompt,assignPath,visualTransform,pathDistance,drawingTrace,observerRect};
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
  root.PathStudioCore=api;
})(typeof window==='undefined'?globalThis:window);
