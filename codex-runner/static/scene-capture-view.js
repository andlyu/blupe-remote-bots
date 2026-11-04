import * as T from './path-studio-three.js';
import {STLLoader} from './path-studio-stl.js';
export function createCaptureView(viewport){
  const C=window.PathStudioCore;C.setStation('yam-1');
  const renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor('#17231a');renderer.outputColorSpace=T.SRGBColorSpace;viewport.append(renderer.domElement);
  const scene=new T.Scene();scene.add(new T.HemisphereLight('#f3f5e6','#364434',2.4));const light=new T.DirectionalLight('#fff6dc',3);light.position.set(.3,-.8,2);scene.add(light);
  const table=new T.Mesh(new T.BoxGeometry(.9,.9,.02),new T.MeshStandardMaterial({color:'#b6b5a5',roughness:1}));table.position.set(.48,0,-.012);scene.add(table);
  const colors=['#ba4c34','#b5b546','#34786b','#4166ab'];
  for(let i=0;i<4;i++)for(let j=0;j<3;j++){const h=.025+.012*((i+j)%3),box=new T.Mesh(new T.BoxGeometry(.044,.044,h*2),new T.MeshStandardMaterial({color:colors[(i+j)%4],roughness:.8}));box.position.set(.36+i*.113,-.25+j*.25,h);scene.add(box);}
  const loader=new STLLoader(),model=window.PathStudioYamModel,geometries=Object.fromEntries(Object.entries(model.meshes).map(([n,b])=>[n,loader.parse(Uint8Array.from(atob(b),c=>c.charCodeAt(0)).buffer)]));
  const body=new T.MeshStandardMaterial({color:'#4b5358',metalness:.4,roughness:.45}),jaw=new T.MeshStandardMaterial({color:'#30383c',metalness:.3,roughness:.5});
  const arms=['left','right'].map(side=>{const group=new T.Group();group.position.set(0,side==='left'?.25:-.25,0);scene.add(group);return model.visuals.map(spec=>{const mesh=new T.Mesh(geometries[spec.mesh],spec.mesh.startsWith('linear_')?jaw:body);mesh.matrixAutoUpdate=false;group.add(mesh);return{mesh,spec,index:spec.frame==='base_link'?-1:Number(spec.frame.replace('link',''))-1};});});
  const overview=new T.PerspectiveCamera(44,1,.01,8);overview.up.set(0,0,1);overview.position.set(1.2,-1.25,1.0);overview.lookAt(.36,0,.17);
  const cameras=[new T.PerspectiveCamera(60,16/9,.01,8),new T.PerspectiveCamera(60,16/9,.01,8)];
  const rays=cameras.map((_,i)=>{const a=new T.ArrowHelper(new T.Vector3(0,0,-1),new T.Vector3(),.24,i===0?'#c6f432':'#efb36a',.025,.012);scene.add(a);return a;});
  let mode=innerWidth<660?'overview':'all',last=null,sim=null;
  const controls=document.createElement('div');controls.className='view-controls';controls.setAttribute('role','group');controls.setAttribute('aria-label','Simulation view');
  for(const[key,label]of[['all','Three views'],['overview','3D motion'],['left','Left wrist'],['right','Right wrist']]){const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('aria-pressed',String(mode===key));b.onclick=()=>{mode=key;for(const x of controls.children)x.setAttribute('aria-pressed',String(x===b));render();};controls.append(b);}viewport.parentElement.after(controls);
  function render(){const w=viewport.clientWidth,h=viewport.clientHeight;renderer.setSize(w,h,false);renderer.setScissorTest(true);const selected=mode==='all'?[overview,...cameras]:[mode==='overview'?overview:cameras[mode==='left'?0:1]];
    selected.forEach((camera,i)=>{const x=Math.floor(i*w/selected.length),width=Math.floor((i+1)*w/selected.length)-x;renderer.setViewport(x,0,width,h);renderer.setScissor(x,0,width,h);if(camera===overview){camera.aspect=width/h;}else{camera.aspect=camera.userData.sensorAspect||16/9;const fittedWidth=Math.min(width,h*camera.aspect),fittedHeight=fittedWidth/camera.aspect;renderer.setViewport(x+(width-fittedWidth)/2,(h-fittedHeight)/2,fittedWidth,fittedHeight);}camera.updateProjectionMatrix();rays.forEach(a=>a.visible=camera===overview);renderer.render(scene,camera);});renderer.setScissorTest(false);
    viewport.parentElement.querySelector('.view-labels').hidden=mode!=='all';}
  new ResizeObserver(render).observe(viewport);
  function frame(index){if(!sim)return;index=Math.min(sim.frames.length-1,Math.max(0,index));last=index;const point=sim.frames[index];
    ['left','right'].forEach((side,i)=>{const fk=C.forward(point[side+'_joints_deg'].map(v=>v*Math.PI/180));for(const v of arms[i]){const origin=new T.Matrix4().set(...C.visualTransform(v.spec,point[side+'_gripper']));const base=v.index<0?new T.Matrix4():new T.Matrix4().set(...fk.matrices[v.index]);v.mesh.matrix.copy(base.multiply(origin));}
      const g=sim.cameras[index][i],r=g.rotation,camera=cameras[i];camera.position.set(...g.position_m);const matrix=new T.Matrix4().set(r[0][0],-r[0][1],-r[0][2],0,r[1][0],-r[1][1],-r[1][2],0,r[2][0],-r[2][1],-r[2][2],0,0,0,0,1);camera.quaternion.setFromRotationMatrix(matrix);const intr=sim.intrinsics[side];camera.userData.sensorAspect=intr.image_size[0]/intr.image_size[1];camera.fov=2*Math.atan(intr.image_size[1]/(2*intr.K[1][1]))*180/Math.PI;rays[i].position.copy(camera.position);rays[i].setDirection(new T.Vector3(...g.optical_axis));});render();}
  return {load(value){sim=value;frame(0);},frame};
}


// Same atlas layout as the local playground: decode once, crop all views from
// one immutable frame. The four-camera fallback order is observer/left/top/right.
export function cameraCrop(role,width,height){
  if(width===2560&&height===1080)return{left:[1920,0,640,360],top:[1920,360,640,360],right:[1920,720,640,360]}[role];
  const index={left:1,top:2,right:3}[role];
  return[(index%2)*width/2,Math.floor(index/2)*height/2,width/2,height/2];
}

export function connectCameraPreviews(panels,{
  Hls=globalThis.Hls,document=globalThis.document,
  createVideo=()=>document.createElement('video'),createCanvas=()=>document.createElement('canvas'),createImage=()=>new Image(),
  setTimer=setTimeout,clearTimer=clearTimeout,requestFrame=requestAnimationFrame,cancelFrame=cancelAnimationFrame,
  now=()=>Date.now(),onHealthChange=()=>{}
}={}){
  const video=createVideo(),atlas=createCanvas(),context=atlas.getContext('2d');
  const states=panels.map(p=>({...p,context:p.canvas.getContext('2d'),received:null,source:null,snapshot:null,timer:null,deadline:null}));
  let stopped=false,hls=null,retry=null,watchdog=null,animation=null,generation=0,failures=0;
  let attemptStarted=now(),lastAdvance=now(),lastMediaTime=-1,lastPaint=-Infinity,frame=0,health='connecting';
  video.muted=true;video.autoplay=true;video.playsInline=true;video.className='camera-source';
  video.setAttribute('aria-hidden','true');video.setAttribute('tabindex','-1');
  document.body.append(video);
  const hidden=()=>document.hidden;
  function announce(value){if(health!==value){health=value;onHealthChange(value);}}
  function labels(){
    for(const state of states){
      const age=state.received===null?null:Math.max(0,Math.floor((now()-state.received)/1000));
      const freshVideo=state.source==='video'&&health==='live'&&now()-lastAdvance<4000;
      state.label.textContent=freshVideo?'Live video · delayed':age===null?(health==='paused'?'Preview paused':'Connecting to video…'):
        (state.source==='snapshot'?'Still image':'Video stalled')+' · received '+age+' s ago · '+(health==='paused'?'preview paused':'reconnecting');
      state.empty.hidden=state.received!==null;
      state.canvas.hidden=state.received===null;
    }
  }
  function stopSnapshot(state){
    clearTimer(state.timer);clearTimer(state.deadline);state.timer=state.deadline=null;
    if(state.snapshot){state.snapshot.onload=state.snapshot.onerror=null;state.snapshot.removeAttribute('src');state.snapshot=null;}
  }
  function snapshot(state){
    if(stopped||hidden()||state.snapshot||state.timer!==null||health==='live')return;
    const image=createImage();state.snapshot=image;
    function done(){
      if(state.snapshot!==image)return;
      stopSnapshot(state);
      if(!stopped&&!hidden()&&health!=='live')state.timer=setTimer(()=>{state.timer=null;snapshot(state);},5000);
    }
    state.deadline=setTimer(done,5000);
    image.onload=()=>{
      if(state.snapshot!==image||stopped||hidden()||health==='live')return;
      try{
        state.canvas.width=image.naturalWidth||640;state.canvas.height=image.naturalHeight||360;
        state.context.drawImage(image,0,0,state.canvas.width,state.canvas.height);
        state.received=now();state.source='snapshot';state.canvas.dataset.frameSource='snapshot';labels();
      }finally{done();}
    };
    image.onerror=done;
    image.src='./api/path-studio/cameras/'+state.role+'.jpg?station=yam-1&t='+now();
  }
  function cleanup(){
    generation++;clearTimer(retry);retry=null;
    if(hls){hls.destroy();hls=null;}
    video.onerror=video.onloadedmetadata=video.onprogress=null;
    video.pause();video.removeAttribute('src');video.load();lastMediaTime=-1;
  }
  function reconnect(){
    if(stopped||hidden()||retry!==null)return;
    cleanup();announce('reconnecting');labels();states.forEach(snapshot);
    retry=setTimer(connect,Math.min(8000,1000*2**Math.min(failures++,3)));
  }
  function connect(){
    cleanup();if(stopped||hidden())return;
    const attempt=generation;attemptStarted=lastAdvance=now();
    announce(frame?'reconnecting':'connecting');labels();states.forEach(snapshot);
    video.onerror=()=>{if(attempt===generation)reconnect();};
    const url='./api/path-studio/video/synchronized-hd/index.m3u8';
    const play=()=>video.play().catch(()=>{/* Watchdog retries blocked/stopped playback. */});
    if(Hls?.isSupported()){
      hls=new Hls({enableWorker:false,lowLatencyMode:true,maxBufferLength:4,backBufferLength:0,
        liveSyncMode:'buffered',liveSyncDuration:.5,liveMaxLatencyDuration:1,
        liveSyncOnStallIncrease:0,maxLiveSyncPlaybackRate:1.05});
      hls.on(Hls.Events.ERROR,(_,data)=>{if(attempt===generation&&data.fatal)reconnect();});
      hls.on(Hls.Events.MANIFEST_PARSED,()=>{if(attempt===generation)play();});
      hls.loadSource(url);hls.attachMedia(video);
    }else if(video.canPlayType('application/vnd.apple.mpegurl')){
      const catchUp=()=>{if(attempt!==generation||!video.seekable.length)return;
        const i=video.seekable.length-1,edge=video.seekable.end(i);
        if(video.currentTime===0||edge-video.currentTime>1)video.currentTime=Math.max(video.seekable.start(i),edge-.5);
      };
      video.onloadedmetadata=video.onprogress=catchUp;video.src=url;play();
    }else{announce('unsupported');labels();}
  }
  function paint(){
    if(stopped)return;
    // Consume the video texture even when the source is occluded. Chrome may
    // otherwise stop presenting frames from an offscreen decoder.
    if(!hidden()&&video.readyState>=2&&!video.paused&&video.currentTime!==lastMediaTime&&now()-lastPaint>=125){
      const width=video.videoWidth,height=video.videoHeight;
      if(width&&height){
        if(atlas.width!==width)atlas.width=width;if(atlas.height!==height)atlas.height=height;
        context.drawImage(video,0,0,width,height);frame++;lastMediaTime=video.currentTime;lastAdvance=now();lastPaint=now();failures=0;
        for(const state of states){
          const rect=cameraCrop(state.role,width,height);
          if(state.canvas.width!==rect[2])state.canvas.width=rect[2];if(state.canvas.height!==rect[3])state.canvas.height=rect[3];
          state.context.drawImage(atlas,...rect,0,0,rect[2],rect[3]);
          state.received=now();state.source='video';state.canvas.dataset.frameSource='video';state.canvas.dataset.presentedFrame=String(frame);
          stopSnapshot(state);
        }
        announce('live');labels();
      }
    }
    animation=requestFrame(paint);
  }
  function watch(){
    if(stopped)return;
    if(!hidden()){
      if(now()-lastAdvance>=4000){announce('reconnecting');states.forEach(snapshot);}
      // Give HLS its full 20s startup/recovery window; nonfatal segment errors
      // are handled by hls.js, without repeatedly tearing down a healthy stream.
      if(now()-lastAdvance>=20000&&now()-attemptStarted>=20000)reconnect();
      labels();
    }
    watchdog=setTimer(watch,1000);
  }
  function visibility(){
    if(hidden()){cleanup();states.forEach(stopSnapshot);announce('paused');labels();}
    else connect();
  }
  document.addEventListener('visibilitychange',visibility);
  connect();paint();watchdog=setTimer(watch,1000);
  return{stop(){stopped=true;cleanup();clearTimer(watchdog);cancelFrame(animation);states.forEach(stopSnapshot);document.removeEventListener('visibilitychange',visibility);video.remove();}};
}
