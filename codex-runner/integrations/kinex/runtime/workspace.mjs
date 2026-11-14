import path from 'node:path';
import {mkdir, copyFile, writeFile} from 'node:fs/promises';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const require = createRequire(path.join(process.env.KINEX_SOURCE, 'package.json'));
const {createKinexRuntime} = await import(pathToFileURL(path.join(process.env.KINEX_SOURCE,'node_modules/@kinex/core/dist/index.js')));
let input = ''; for await (const chunk of process.stdin) input += chunk;
const config = JSON.parse(input);
await mkdir(config.directory,{recursive:true});
const runtime = createKinexRuntime({directory: config.directory});
await runtime.profiles.writeManifest({identity:{id:config.robot_id||'yam-1',name:config.robot_id==='robot-ba8413962083809c'?'Robo-house YAM':'BluPe YAM1',platform:'real',kind:'arm',model:'YAM'},
  safety:{max_joint_velocity:.35, max_cartesian_velocity:'???',keep_out_zones:[]}});
const affected = ['left_arm','right_arm','left_gripper','right_gripper'];
const stop = {behavior:'controller_emergency_stop',affected_devices:affected};
for (const name of [...affected,'top_camera','left_camera','right_camera','world']) {
  const camera = name.endsWith('_camera');
  const world = name === 'world';
  const joint = name.endsWith('_arm');
  const side = name.split('_')[0];
  const actions = world ? ['read','wait','load','unload','status'] : camera ? ['read','load','unload','status'] : ['read','write','stop','load','unload','status'];
  const profile = {name,type:world?'world':camera?'rgb':joint?'joint':'gripper',loaded:true,
    access:{connection:world?{kind:'process'}:{kind:'url',url:process.env.BLUPE_KINEX_BRIDGE||'http://127.0.0.1:1'},driver:{entry:'driver.py',interpreter:process.env.BLUPE_KINEX_PYTHON,actions,persistent:true,timeout_s:30}},intrinsics:{}};
  if (joint) profile.intrinsics = {model:{format:'joints',joints:Array.from({length:6},(_,i)=>({
    name:side+'_joint'+(i+1),type:'revolute',limits:{min:config.limits.lower_rad[(side==='left'?0:6)+i],max:config.limits.upper_rad[(side==='left'?0:6)+i]},max_velocity:.35,max_effort:null}))},
    control:{mode:'position'},feedback:{velocities:false,efforts:false},stop,home:null,kinematics:null};
  else if (!world && !camera) profile.intrinsics = {control:{mode:'position',units:'normalized',bounds:{min:0,max:1},resolution:null,open_target:1,close_target:0,speed:null},feedback:{aperture_m:false},stop};
  else if (camera) profile.intrinsics = {color:{width:config.cameras[side].width,height:config.cameras[side].height,fps:null,projection:'???',distortion:'???',fov:'???',pixel_format:'rgb8',image_format:'png'}};
  if (!world) profile.extrinsics = {};
  await runtime.profiles.writeDevice(profile);
  await copyFile(path.join(path.dirname(fileURLToPath(import.meta.url)),'driver.py'),path.join(config.directory,'.kinex/devices',name,'driver.py'));
}
await writeFile(path.join(config.directory,'.kinex/kinex.json'),JSON.stringify({permission:{shell:'deny',write:'deny',edit:'deny',profile_write:'deny',setup_plan:'deny'}}));
await runtime.dispose();
process.stdout.write(JSON.stringify({ready:true,devices:8})+'\n');
