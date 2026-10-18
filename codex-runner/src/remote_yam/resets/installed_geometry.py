#!/usr/bin/env python3
"""Offline installed-jaw and carried-cube sweep audit. Never opens robot I/O."""
import argparse,copy,hashlib,importlib.util,json,math,sys,time
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import mujoco
from scipy.spatial.transform import Rotation
from remote_yam.resets.station import resource
from remote_yam.resets.yam_cube_reset import plain,load_targets
from remote_yam.resets.yam_cube_contact import reference_contact
from remote_yam.resets.yam_cube_sizes import edge_m,validate_edges,resize_targets

_MODEL_CACHE={}


def model_key(xml,*,include_assets):
 digest=hashlib.sha256(xml.encode())
 if include_assets:
  # Inline XML can retain mesh filenames; bind their actual contents too.
  # A file edit must never silently reuse an older collision model.
  document=ET.fromstring(xml);compiler=document.find('compiler')
  settings=compiler.attrib if compiler is not None else {}
  for node in document.findall('asset/*'):
   if node.get('file'):
    file=Path(node.get('file'))
    if not file.is_absolute():
     field='meshdir' if node.tag=='mesh' else 'texturedir' if node.tag=='texture' else 'assetdir'
     file=Path(settings.get(field,settings.get('assetdir','.')))/file
    file=file.resolve(strict=True)
    digest.update(str(file).encode());digest.update(hashlib.sha256(file.read_bytes()).digest())
 return digest.hexdigest()


def compile_model(xml,*,reuse=False):
 key=model_key(xml,include_assets=reuse)
 if reuse and key in _MODEL_CACHE:return _MODEL_CACHE[key],True
 model=mujoco.MjModel.from_xml_string(xml)
 if reuse:
  if len(_MODEL_CACHE)>=8:_MODEL_CACHE.pop(next(iter(_MODEL_CACHE)))
  _MODEL_CACHE[key]=model
 return model,False


def minimum_vertex_z(vertices,geom_ids,geom_xmat,geom_xpos):
 return float(np.min(np.einsum('ij,ij->i',vertices,geom_xmat[geom_ids,6:9])+geom_xpos[geom_ids,2]))


def grasp_attachment(tip,rotation,center,cube_rotation):
 """Keep the actual cube pose continuous when the audited grasp begins."""
 return rotation.T@(center-tip),rotation.T@cube_rotation


def validate_tangential_offset(offset,grip_rotation,source_yaw,reference,edge=.030):
 assert math.isfinite(offset) and abs(offset)<=.015
 relative=grip_rotation.T@Rotation.from_euler('z',source_yaw).as_matrix()
 half=edge/2*np.sum(np.abs(relative[0]))
 opening_width=edge*np.sum(np.abs(relative[1]))
 # A corner pinch must retain the two opening-axis extrema inside the pads.
 if opening_width>.031:assert abs(offset)<=.01
 for tip in reference['tips']:
  bounds=np.array(tip['pad_bounds_native_grasp_m'])
  overlap=min(bounds[1,0],-offset+half)-max(bounds[0,0],-offset-half)
  assert overlap>=.010,'Tangential pad overlap below10mm'


def intended_tip_contact_kind(names,side,color,stage,plan,native,pad,pad_y,aperture,reference,distance):
 """Classify only selected-cube/active-tip contact, including bounded preload edges."""
 tipname=next((n for n in names if n.startswith(side+'_installed_tip_left_') or n.startswith(side+'_installed_tip_right_')),None)
 if len(names)!=2 or not tipname or 'cube_'+color not in names:return None
 if not (stage.get('carrying') or stage.get('intended_selected_contact')):return None
 bounds=np.asarray(pad['pad_bounds_native_grasp_m']);native=np.asarray(native)
 if not np.all(np.isfinite(native)) or not math.isfinite(distance):return None
 if abs(native[1]-pad_y)>.001:return None
 # Preserve the existing pad patch policy exactly.
 if distance>=-.001 and all(bounds[0,k]-.001<=native[k]<=bounds[1,k]+.001 for k in [0,2]):return 'pad'
 compression=float(plan.get('grasp_compression_m',0.));relief=float(plan.get('grasp_gap_relief_m',0.))
 geometry=plan['contact_geometry'];width=float(geometry['projected_grasp_width_m'])
 edge_bound=float(geometry['candidate_vertical_error_bound_m'])
 values=(compression,relief,width,edge_bound,aperture,pad_y)
 if not all(math.isfinite(v) for v in values):return None
 if not (0<compression<=.002 and 0<=relief<=.0002 and width>0 and 0<=edge_bound<=.002):return None
 gap=lambda a:reference['closed_gap_m']+reference['opening_travel_m']*a
 # Release starts at the previous carry aperture. Admit only that unloading
 # transition while preload remains, never an opening-stage collision later.
 unloading=(stage['name']=='release' and stage.get('intended_selected_contact') and
            'grippers' in stage and gap(stage['grippers'][0 if side=='left' else 1])>=width)
 if stage['name']!='close' and not stage.get('carrying') and not unloading:return None
 commanded=width-compression+relief
 if abs(gap(geometry['nominal_aperture'])-commanded)>1e-9:return None
 effective=width-gap(aperture)
 if not 0<effective<=compression-relief+1e-6:return None
 # Each jaw can indent only its share of actual commanded preload. Retain
 # the old 1mm depth ceiling and front-plane band; extend only the pad edge
 # to the existing <=2mm contact-height uncertainty, never to the whole tip.
 if distance < -min(.001,effective/2+1e-6):return None
 if not all(bounds[0,k]-edge_bound<=native[k]<=bounds[1,k]+edge_bound for k in [0,2]):return None
 return 'preload_edge'


def contact_blocked_aperture(plan,stage,aperture,reference):
 """Offline loaded-grasp hypothesis; never rewrites a native command.

 A position setpoint beyond contact does not imply rigid-cube deformation.
 Use the separately declared bounded CAD contact aperture for loaded jaws.
 """
 command_gap=plan.get('grasp_command_gap_m')
 if command_gap is None:return aperture
 geometry=plan['contact_geometry'];width=geometry['projected_grasp_width_m']
 gap=lambda a:reference['closed_gap_m']+reference['opening_travel_m']*a
 contact=geometry['nominal_aperture'];compression=plan['grasp_compression_m'];relief=plan['grasp_gap_relief_m']
 assert all(math.isfinite(v) for v in (command_gap,contact,compression,relief))
 assert 0<=compression<=.002 and 0<=relief<=.0002
 assert abs(gap(contact)-(width-compression+relief))<1e-9
 assert 0<=geometry['commanded_aperture']<=1 and abs(gap(geometry['commanded_aperture'])-command_gap)<1e-9
 closing=stage['name']=='close' or stage.get('carrying')
 index=0 if plan['arm']=='left' else 1
 unloading=stage['name']=='release' and stage.get('intended_selected_contact') and gap(stage['grippers'][index])>=width
 if closing:
  assert abs(gap(stage['grippers'][index])-command_gap)<1e-9
 if closing or unloading:return max(aperture,contact)
 return aperture


def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--preview',type=Path,required=True);p.add_argument('--parts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-initial-object-touch',action='store_true');p.add_argument('--allow-staging',action='store_true');p.add_argument('--reuse-model',action='store_true');p.add_argument('--stop-on-failure',action='store_true');a=p.parse_args(argv)
 started=time.monotonic();preview=json.loads((a.preview/'result.json').read_text());scene=json.loads((a.preview/'planning-scene.json').read_text());state=json.loads((a.preview/'controller-state.json').read_text());report=json.loads((a.preview/'calibration.json').read_text());ref=reference_contact(a.runtime_root)
 goals_path=Path(resource('goals_path'))
 final_record=load_targets(goals_path);final_goals=final_record['targets']
 assert preview['targets_sha256']==final_record['content_sha256'],'Final task goal content changed'
 edges=preview['plans'][0].get('qualification_cube_edges_m')
 if edges is not None:
  edges=validate_edges(edges)
  assert all(plan.get('qualification_cube_edges_m')==edges for plan in preview['plans'])
  assert all(edge_m(scene[c])==edges[c] for c in scene),'Scene dimensions differ from declared size case'
  final_record=resize_targets(final_record,edges,report);final_goals=final_record['targets']
 planning_targets=None
 if a.allow_staging:
  planning_targets=json.loads((a.preview/'planning-targets.json').read_text())
  assert planning_targets['planning_only'] and planning_targets['final_task_targets_sha256']==preview['targets_sha256']
 for plan in preview['plans']:
  c=plan['color'];destination=plan.get('destination_scene_row',final_goals[c])
  if destination.get('planning_goal_kind')=='staging':
   assert a.allow_staging and planning_targets['targets'][c]==destination
   assert destination['declared_height_m']==edge_m(scene[c]) and destination['support_plane_left']==[0.,0.,0.]
  else:assert destination==final_goals[c]
  if planning_targets is not None:
   assert planning_targets['targets'][c]==destination
   assert all(planning_targets['targets'][other]==final_goals[other] for other in final_goals if other!=c)

 from remote_yam.mujoco_ik import default_scene_path,ROBOT_SHA256
 from remote_yam.resets.kinematics import arm_pose
 src=default_scene_path().with_name('yam_bimanual.xml');assert hashlib.sha256(src.read_bytes()).hexdigest()==ROBOT_SHA256
 repair=Path(resource('collision_model_source'));spec=importlib.util.spec_from_file_location('cube_collision_repair',repair);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 root=module._expanded_xml(src);root.remove(root.find('keyframe'));world=root.find('worldbody');contact=ET.SubElement(root,'contact');ET.SubElement(world,'geom',name='table',type='plane',size='2 2 .01')
 stock=ET.parse(Path(ref['asset_directory'])/'linear_4310.xml').getroot();manifest=json.loads((a.parts/'manifest.json').read_text());meshes={}
 for m in stock.findall('asset/mesh'):
  name=m.get('name')
  if name.startswith('tip_'):
   row=manifest['meshes'][name];assert row['source_sha256']==ref['asset_sha256'][name+'.stl']
   meshes[name]=[]
   for i,item in enumerate(row['parts']):
    file=a.parts/item['file'];assert hashlib.sha256(file.read_bytes()).hexdigest()==item['sha256'];n=f'installed_{name}_{i}'
    ET.SubElement(root.find('asset'),'mesh',name=n,file=str(file.resolve()));meshes[name].append(n)
  else:
   meshes[name]=['installed_'+name];ET.SubElement(root.find('asset'),'mesh',name='installed_'+name,file=str(Path(ref['asset_directory'])/m.get('file')))
 spacing=report['base_geometry']['spacing_m']
 for side,sign in [('left',1),('right',-1)]:
  link=root.find(".//body[@name='"+side+"_link1']");old=np.fromstring(link.get('pos'),sep=' ');delta=sign*spacing/2-old[1];old[1]+=delta;link.set('pos',' '.join(map(str,old)))
  for geom in world.findall('geom'):
   if geom.get('mesh')==side+'_base':
    pos=np.fromstring(geom.get('pos'),sep=' ');pos[1]+=delta;geom.set('pos',' '.join(map(str,pos)))
  grasp=root.find(".//body[@name='"+side+"_grasp']")
  for geom in list(grasp.findall('geom')):grasp.remove(geom)
  mount=copy.deepcopy(stock.find('worldbody/body'))
  for body in list(mount.iter('body')):
   for geom in list(body.findall('geom')):
    name=geom.get('mesh');body.remove(geom)
    for i,mesh in enumerate(meshes[name]):
     part=copy.deepcopy(geom);part.set('mesh',mesh);part.set('name',f'{side}_installed_{name}_{i}');part.set('contype','1');part.set('conaffinity','1');part.set('mass','0');body.append(part)
  for node in mount.iter():
   if node.tag!='geom' and 'name' in node.attrib:node.set('name',side+'_installed_'+node.get('name'))
  root.find(".//body[@name='"+side+"_link6']").append(mount)
  for exc in stock.findall('contact/exclude'):ET.SubElement(contact,'exclude',body1=side+'_installed_'+exc.get('body1'),body2=side+'_installed_'+exc.get('body2'))
 module.declare_base_adjacency(root)
 for color,row in scene.items():
  point=np.array(row['visible_top_center_by_arm']['left']['top_center_m']);point[1]+=spacing/2;point[2]=row['visible_top_center_by_arm']['left']['support_point_m'][2]+edge_m(row)/2
  body=ET.SubElement(world,'body',name='cube_'+color,pos=' '.join(map(str,point)));ET.SubElement(body,'freejoint',name='cube_'+color);ET.SubElement(body,'geom',name='cube_'+color,type='box',size=' '.join([str(edge_m(row)/2)]*3),mass='.04')
 model,reused=compile_model(ET.tostring(root,encoding='unicode'),reuse=a.reuse_model);module.synchronize_collision_masks(model);data=mujoco.MjData(model)
 qids=np.array([model.joint(f'{s}_joint{i}').qposadr[0] for s in ['left','right'] for i in range(1,7)])
 gripper_ids=[g for g in range(model.ngeom) if '_installed_' in model.body(model.geom_bodyid[g]).name];vertices={g:model.mesh_vert[model.mesh_vertadr[model.geom_dataid[g]]:model.mesh_vertadr[model.geom_dataid[g]]+model.mesh_vertnum[model.geom_dataid[g]]] for g in gripper_ids}
 vertex_stack=np.concatenate(list(vertices.values()))
 vertex_geom_ids=np.repeat(list(vertices),[len(v) for v in vertices.values()])
 def cube_pose(color,pos,rot):
  j=model.joint('cube_'+color).qposadr[0];quat=Rotation.from_matrix(rot).as_quat();data.qpos[j:j+7]=np.r_[pos,quat[[3,0,1,2]]]
 def set_scene():
  for color,row in scene.items():
   pos=np.array(row['visible_top_center_by_arm']['left']['top_center_m']);pos[1]+=spacing/2;pos[2]=row['visible_top_center_by_arm']['left']['support_point_m'][2]+edge_m(row)/2;cube_pose(color,pos,Rotation.from_euler('z',row['yaw_rad']).as_matrix())
 q=np.array(state['joints']);g=np.array([state['left_gripper'],state['right_gripper']]);rows=[];failures=[];set_scene()
 touch=None
 if a.allow_initial_object_touch:
  from remote_yam.resets.yam_cube_touch import InitialTouchAllowance,scene_boxes
  touch=InitialTouchAllowance(scene_boxes(scene,spacing))
 def boxes():
  return {c:dict(center=data.geom_xpos[model.geom('cube_'+c).id].copy(),rotation=data.geom_xmat[model.geom('cube_'+c).id].reshape(3,3).copy(),half_size=model.geom_size[model.geom('cube_'+c).id].copy()) for c in scene}
 for plan in preview['plans']:
  color=plan['color'];side=plan['arm'];idx=0 if side=='left' else 1;inactive=slice(6,12) if idx==0 else slice(0,6);initial=q.copy();contact_geometry=plan['contact_geometry'];error=contact_geometry['candidate_vertical_error_bound_m'];tcp=contact_geometry['tcp_height_above_support_m'];site=model.site(side+'_installed_grasp_site').id
  destination=plan.get('destination_scene_row',final_goals[color])
  wanted_place=np.array(destination['visible_top_center_by_arm']['left']['top_center_m']);wanted_place[1]+=spacing/2;wanted_place[2]=destination['visible_top_center_by_arm']['left']['support_point_m'][2]+tcp
  declared_place=next(s for s in plan['stages'] if s['name']=='place')
  offset=float(plan.get('grasp_offset_native_x_m',0.))
  close_rotation=np.array(next(s['expected_rotation'] for s in plan['stages'] if s['name']=='close'))
  validate_tangential_offset(offset,close_rotation,scene[color]['yaw_rad'],ref,edge_m(scene[color]))
  release_clearance=float(plan.get('release_clearance_m',0.))
  assert math.isfinite(release_clearance) and 0<=release_clearance<=.0005
  wanted_place[2]+=release_clearance
  wanted_place+=np.array(declared_place['expected_rotation'])[:,0]*offset
  assert np.linalg.norm(np.array(declared_place['expected_tip_world_m'])-wanted_place)<1e-9
  relative_pos=relative_rot=None
  for stage in plan['stages']:
   minimum=100.;carry_min=100.;samples=0;pad_contacts=0;preload_edges=0;maxfk=0.;bad=[];command_min=100.;model_min=100.
   for target in stage['points_rad']:
    target=np.array(target);endg=np.array(stage['grippers']);count=max(1,math.ceil(np.max(abs(target-q))/.005),math.ceil(np.max(abs(endg-g))/.05))
    for alpha in np.linspace(0,1,count+1):
     current=q+alpha*(target-q);jaws=g+alpha*(endg-g);assert np.array_equal(current[inactive],initial[inactive]);data.qpos[qids]=current
     command_min=min(command_min,float(ref['closed_gap_m']+ref['opening_travel_m']*jaws[idx]))
     jaws[idx]=contact_blocked_aperture(plan,stage,jaws[idx],ref)
     model_min=min(model_min,float(ref['closed_gap_m']+ref['opening_travel_m']*jaws[idx]))
     for i,s in enumerate(['left','right']):
      for joint in ['joint7','joint8']:data.qpos[model.joint(s+'_installed_'+joint).qposadr[0]]=.0475*jaws[i]
     mujoco.mj_forward(model,data)
     tip=data.site_xpos[site].copy();r=data.site_xmat[site].reshape(3,3).copy()
     if stage.get('carrying'):
      if relative_pos is None:
       held=boxes()[color];relative_pos,relative_rot=grasp_attachment(tip,r,held['center'],held['rotation'])
      cube_pose(color,tip+r@relative_pos,r@relative_rot);mujoco.mj_forward(model,data)
     if touch is not None:touch.update(boxes(),selected=color if stage.get('carrying') or stage.get('intended_selected_contact') else None)
     for i,s in enumerate(['left','right']):
      expected=arm_pose(report,{s+'_joints_deg':np.rad2deg(current[i*6:i*6+6])},s)[:3,3];actual=data.site_xpos[model.site(s+'_installed_grasp_site').id];maxfk=max(maxfk,float(np.linalg.norm(expected-actual)))
     minimum=min(minimum,minimum_vertex_z(vertex_stack,vertex_geom_ids,data.geom_xmat,data.geom_xpos))
     if stage.get('carrying'):
      cid=model.geom('cube_'+color).id;cr=data.geom_xmat[cid].reshape(3,3);bottom=data.geom_xpos[cid,2]-abs(cr[2])@model.geom_size[cid];carry_min=min(carry_min,float(bottom))
     for c in data.contact:
      ids=[int(c.geom1),int(c.geom2)];names=[model.geom(i).name for i in ids]
      if touch is not None and all(n.startswith('cube_') for n in names):
       if touch.allows(names[0][5:],names[1][5:],float(c.dist)):continue
      if 'table' in names and any(n.startswith('cube_') for n in names):
       cube=next(n[5:] for n in names if n.startswith('cube_'))
       if cube!=color or not stage.get('carrying') or stage.get('intended_selected_contact'):
        if c.dist>=-1e-6:continue
      tipname=next((n for n in names if n.startswith(side+'_installed_tip_')),None)
      if tipname and 'cube_'+color in names and (stage.get('carrying') or stage.get('intended_selected_contact')):
       native=(c.pos-tip)@r;which='tip_left' if '_tip_left_' in tipname else 'tip_right';pad=next(t for t in ref['tips'] if t['name']==which);bounds=np.array(pad['pad_bounds_native_grasp_m']);py=pad['pad_y_m']+(.0475*jaws[idx] if which=='tip_left' else -.0475*jaws[idx])
       kind=intended_tip_contact_kind(names,side,color,stage,plan,native,pad,py,jaws[idx],ref,float(c.dist))
       if kind:
        pad_contacts+=1;preload_edges+=int(kind=='preload_edge');continue
      bad.append(dict(geoms=names,distance_m=float(c.dist),stage=stage['name'],sample=samples))
     samples+=1
    q=target;g=endg
   destination_error=float(np.linalg.norm(tip-wanted_place)) if stage['name']=='place' else 0.
   status='PASS' if destination_error<=.002 and not bad and (touch is None or touch.verdict()['passed']) and minimum-error>=.005-1e-9 and maxfk<1e-5 and (not stage.get('carrying') or carry_min>=(-1e-6 if stage.get('intended_selected_contact') else .004)) else 'BLOCKED'
   row=dict(color=color,stage=stage['name'],state=status,samples=samples,min_installed_gripper_z_m=minimum,minimum_after_assumed_height_error_m=minimum-error,held_cube_min_z_m=carry_min if stage.get('carrying') else None,pad_contact_samples=pad_contacts,preload_edge_contact_samples=preload_edges,min_commanded_jaw_gap_m=command_min,min_modeled_jaw_gap_m=model_min,max_fk_disagreement_m=maxfk,unexpected_contact_count=len(bad),unexpected_contacts=bad[:12],inactive_arm_exact=True)
   rows.append(row)
   if stage['name']=='place':row['destination_tip_error_m']=destination_error
   if status!='PASS':
    failures.append(row)
    if a.stop_on_failure:break
  if failures and a.stop_on_failure:break
  # Freeze released cube at the actual planned placement for subsequent paths.
  placedrot=np.array(next(s['expected_rotation'] for s in plan['stages'] if s['name']=='place'))
  target=copy.deepcopy(plan.get('destination_scene_row',final_goals[color]));target['yaw_rad']=float(Rotation.from_matrix(placedrot@relative_rot).as_euler('zyx')[0]);scene[color]=target
  set_scene()
 result=dict(scope='Offline exact installed CAD with separate CoACD convex parts; nominal cube contact and assumed vertical error only, no physical contact/force certification',preview_result_sha256=hashlib.sha256((a.preview/'result.json').read_bytes()).hexdigest(),targets_sha256=preview['targets_sha256'],physical_motion_sent=False,complete=not failures,rows=rows,summary=dict(passed=sum(r['state']=='PASS' for r in rows),blocked=len(failures),swept_samples=sum(r['samples'] for r in rows)),elapsed_s=time.monotonic()-started,collision_loader_sha256=hashlib.sha256(repair.read_bytes()).hexdigest(),decomposition_manifest_sha256=hashlib.sha256((a.parts/'manifest.json').read_bytes()).hexdigest())
 result['qualification_cube_edges_m']=edges
 result['derived_targets_sha256']=final_record['content_sha256']
 result['auditor_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 result['input_sha256']={name:hashlib.sha256((a.preview/name).read_bytes()).hexdigest() for name in ('result.json','planning-scene.json','controller-state.json','calibration.json')}
 if a.allow_staging:result['input_sha256']['planning-targets.json']=hashlib.sha256((a.preview/'planning-targets.json').read_bytes()).hexdigest()
 result['initial_object_touch']=touch.verdict() if touch is not None else None
 result['model_reused']=reused
 result['stopped_on_first_failure']=bool(failures and a.stop_on_failure)
 with a.output.open('x') as f:json.dump(plain(result),f,indent=2)
 print(json.dumps(dict(summary=result['summary'],elapsed_s=result['elapsed_s'],blocked_stages=[dict(color=r['color'],stage=r['stage'],contacts=r['unexpected_contacts'][:2],floor=r['minimum_after_assumed_height_error_m']) for r in failures]),indent=2))
 return 0 if result['complete'] else 2
if __name__=='__main__':raise SystemExit(main())
