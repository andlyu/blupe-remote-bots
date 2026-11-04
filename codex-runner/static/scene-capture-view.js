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
