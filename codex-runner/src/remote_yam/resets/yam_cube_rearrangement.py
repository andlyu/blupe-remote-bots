"""Offline tabletop staging, with every pick/place independently CAD audited."""
import copy
import math
from pathlib import Path
import shutil
import json
import hashlib
import numpy as np
from .yam_cube_program import save
from .yam_cube_reset import ResetBlocked
from .yam_cube_scenes import synthetic_scene,box_separation,rotation


def plan_rearrangement(program,state,scene,output,*,remaining_colors=None,first_leg_only=False):
    output=Path(output);state=copy.deepcopy(state);scene=copy.deepcopy(scene)
    final_targets=copy.deepcopy(program.targets)
    program.planner.shared_path_cache={}
    remaining=list(remaining_colors) if remaining_colors is not None else ['blue','orange','yellow']
    if len(set(remaining))!=len(remaining) or any(c not in ('blue','orange','yellow') for c in remaining):
        raise ResetBlocked('Invalid remaining cube set')
    sequence=[];attempts=[];staged=set();stage_count=0
    orthogonal_staging=bool(getattr(program.planner,'orthogonal_staging',False))
    uncertainty_staged=set();last_stage_grasp_yaw={}
    buffers=[(.18,0.),(.22,0.),(.18,.08),(.18,-.08),(.22,.08),(.22,-.08)]
    searches=([((.08,.05,.12),(0.,math.pi/2,-math.pi/2,math.pi))] if getattr(program.planner,'geometry_grasps',False) else
              [((.08,),(0.,math.pi/2,-math.pi/2,math.pi)),
               ((.05,.12),tuple(i*math.pi/4 for i in range(-4,4)))])

    checkpoint=output/'planning-sequence.json'
    if checkpoint.exists():
        saved=json.loads(checkpoint.read_text())
        for index,entry in enumerate(saved,1):
            color=entry['color'];folder=output/entry['directory']
            if entry['leg_id']!=index or entry['directory']!=f'leg-{index:02d}-{color}-plan':
                raise ResetBlocked('Invalid resumed leg identity')
            plan=json.loads((folder/'result.json').read_text())['plans'][0]
            audit=json.loads((folder/'installed-audit.json').read_text())
            bindings=audit.get('input_sha256',{})
            if not audit['complete'] or not bindings or any(hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest for name,digest in bindings.items()):
                raise ResetBlocked('Resumed leg lacks an unchanged complete geometry audit')
            if json.loads((folder/'controller-state.json').read_text())!=state or json.loads((folder/'planning-scene.json').read_text())!=scene:
                raise ResetBlocked('Resumed leg does not continue the fixed scene and state')
            target=plan['destination_scene_row'];kind=target.get('planning_goal_kind','goal')
            if plan['color']!=color or entry['goal_kind']!=kind or (color not in remaining and not (kind=='staging' and getattr(program.planner,'allow_goal_blocker_staging',False))):
                raise ResetBlocked('Invalid resumed color or goal kind')
            if kind=='goal':
                if target!=final_targets['targets'][color]:raise ResetBlocked('Resumed leg changes final task goals')
                remaining.remove(color)
            elif kind=='staging':
                if color not in remaining:remaining.append(color)
                stage_count+=1;point=program.planner.world(target);staged.add((color,float(point[0]),float(point[1])))
                if orthogonal_staging:
                    uncertainty_staged.add(color)
                    rotation_at_place=next(s['expected_rotation'] for s in plan['stages'] if s['name']=='place')
                    last_stage_grasp_yaw[color]=math.atan2(rotation_at_place[1][0],rotation_at_place[0][0])
            else:raise ResetBlocked('Unknown resumed destination kind')
            state['joints']=copy.deepcopy(plan['final_joints'])
            state['left_gripper'],state['right_gripper']=plan['final_grippers']
            yaw=scene[color]['yaw_rad']+plan.get('destination_yaw_offset_rad',0.)
            scene[color]=copy.deepcopy(target);scene[color]['yaw_rad']=yaw
            sequence.append(entry)

    def attempt(color,target,kind,heights,yaws):
        folder=output/f'attempt-{len(attempts)+1:03d}-{color}-{kind}'
        folder.mkdir();program.out=folder
        program.targets=copy.deepcopy(final_targets)
        program.targets['targets'][color]=copy.deepcopy(target)
        program.planner.destination_grasp_yaws=yaws
        program.planner.transfer_height_margins=heights
        program.planner.cache_paths=True
        previous_required=getattr(program.planner,'required_grasp_yaw_rad',None)
        if orthogonal_staging and color in last_stage_grasp_yaw:
            program.planner.required_grasp_yaw_rad=last_stage_grasp_yaw[color]+math.pi/2
        try:plan=program.make_plan(color,scene,state)
        except ResetBlocked as exc:
            attempts.append(dict(color=color,goal_kind=kind,passed=False,error=str(exc)))
            save(output/'scheduling.json',dict(sequence=sequence,attempts=attempts))
            return None
        finally:
            program.targets=copy.deepcopy(final_targets)
            program.planner.required_grasp_yaw_rad=previous_required
        attempts.append(dict(color=color,goal_kind=kind,passed=True))
        return color,plan,folder,target,kind

    def commit(choice):
        color,plan,folder,target,kind=choice
        if kind=='staging' and color not in remaining:remaining.append(color)
        directory=f'leg-{len(sequence)+1:02d}-{color}-plan'
        shutil.copytree(folder/(color+'-plan'),output/directory)
        sequence.append(dict(leg_id=len(sequence)+1,color=color,directory=directory,goal_kind=kind))
        if kind=='staging' and orthogonal_staging:
            uncertainty_staged.add(color)
            rotation_at_place=next(s['expected_rotation'] for s in plan['stages'] if s['name']=='place')
            last_stage_grasp_yaw[color]=math.atan2(rotation_at_place[1][0],rotation_at_place[0][0])
        state['joints']=copy.deepcopy(plan['final_joints'])
        state['left_gripper'],state['right_gripper']=plan['final_grippers']
        yaw=scene[color]['yaw_rad']+plan.get('destination_yaw_offset_rad',0.)
        scene[color]=copy.deepcopy(target);scene[color]['yaw_rad']=yaw
        save(output/'planning-sequence.json',sequence)
        save(output/'scheduling.json',dict(sequence=sequence,attempts=attempts))

    from .yam_cube_sizes import edge_m

    def buffer_target(color,x,y):
        half=edge_m(scene[color])/2
        if (color,x,y) in staged:return None
        for other,row in scene.items():
            if other==color:continue
            p=program.planner.world(row)
            other_half=edge_m(row)/2
            if box_separation([x,y,half],rotation(0.),[half]*3,p[:2].tolist()+[other_half],rotation(row['yaw_rad']),[other_half]*3)<.025:return None
        current=program.planner.world(scene[color])
        if math.hypot(current[0]-x,current[1]-y)<.04:return None
        target=synthetic_scene(dict(objects=[dict(color=color,center_world_m=[x,y,half],yaw_rad=0.,edge_m=2*half)]),program.report)[color]
        target['planning_goal_kind']='staging'
        return target

    while remaining:
        if first_leg_only and sequence:
            break
        choice=None
        def distance(color):
            return float(sum((a-b)**2 for a,b in zip(program.planner.world(scene[color]),program.planner.world(final_targets['targets'][color]))))
        def pickup_blocking_count(color):
            clearance=float(getattr(program.planner,'preserve_pickup_clearance_m',0.))
            return sum(other!=color and np.linalg.norm(program.planner.world(final_targets['targets'][other])[:2]-program.planner.world(scene[color])[:2])<clearance for other in remaining)
        def priority(color):
            preferred=getattr(program.planner,'preferred_color_order',())
            rank=(preferred.index(color) if color in preferred else len(preferred),) if preferred else ()
            if not getattr(program.planner,'least_contact_first',False):return (*rank,distance(color))
            half=edge_m(scene[color])/2
            center=program.planner.world(scene[color]).copy();center[2]=half
            contacts=0;nearest=float('inf')
            for other,row in scene.items():
                if other==color:continue
                other_half=edge_m(row)/2
                neighbor=program.planner.world(row).copy();neighbor[2]=other_half
                gap=box_separation(center,rotation(scene[color]['yaw_rad']),[half]*3,neighbor,rotation(row['yaw_rad']),[other_half]*3)
                contacts+=gap<=.0002;nearest=min(nearest,float(gap))
            return (*rank,contacts,-nearest,distance(color))
        if orthogonal_staging and stage_count<6:
            for color in sorted((c for c in remaining if c not in uncertainty_staged),key=priority):
                for x,y in buffers:
                    target=buffer_target(color,x,y)
                    if target is None:continue
                    choice=attempt(color,target,'staging',(.08,.05),(0.,math.pi/2,-math.pi/2,math.pi))
                    staged.add((color,x,y))
                    if choice:break
                if choice:break
            if choice:
                commit(choice);stage_count+=1;continue
        if not orthogonal_staging and getattr(program.planner,'proactive_staging',False) and stage_count<6:
            crossing=[]
            for color in remaining:
                source=program.planner.world(scene[color]);goal=program.planner.world(final_targets['targets'][color])
                if scene[color].get('planning_goal_kind')!='staging' and source[1]*goal[1]<0 and abs(source[1]-goal[1])>.10:
                    crossing.append(color)
            for color in sorted(crossing,key=priority):
                tried=0
                for x,y in buffers:
                    target=buffer_target(color,x,y)
                    if target is None:continue
                    tried+=1
                    choice=attempt(color,target,'staging',(.08,.05),(0.,math.pi/2,-math.pi/2,math.pi))
                    staged.add((color,x,y))
                    if choice:break
                    if tried>=2:break
                if choice:break
            if choice:
                commit(choice);stage_count+=1;continue
        for heights,yaws in searches:
            for color in sorted(remaining,key=priority):
                if orthogonal_staging and color not in uncertainty_staged:continue
                clearance=float(getattr(program.planner,'preserve_pickup_clearance_m',0.))
                if clearance and any(other!=color and np.linalg.norm(program.planner.world(final_targets['targets'][color])[:2]-program.planner.world(scene[other])[:2])<clearance for other in remaining):
                    continue
                choice=attempt(color,final_targets['targets'][color],'goal',heights,yaws)
                if choice:break
            if choice:break
        if choice:
            commit(choice);remaining.remove(choice[0]);continue
        if stage_count>=6:raise ResetBlocked('Staging move budget exhausted before all final deliveries')
        preserve_access=bool(getattr(program.planner,'preserve_pickup_clearance_m',0.))
        if preserve_access:
            # Break the pickup/goal dependency cycle by moving its blocker.
            # Replanning must not repeatedly shuttle an unrelated cube merely
            # because its final delivery is farther from its current position.
            colors=sorted(remaining,key=lambda c:(scene[c].get('planning_goal_kind')=='staging',-pickup_blocking_count(c),-distance(c)))
            staging_candidates=((color,x,y) for color in colors for x,y in buffers)
        else:
            staging_candidates=((color,x,y) for x,y in buffers for color in sorted(remaining,key=distance,reverse=True))
        for color,x,y in staging_candidates:
                # Do not cycle through the same buffer for a cube. Other cubes
                # must also leave a geometric gap; installed jaw clearance is
                # still resolved by the mandatory complete sweep audit.
                target=buffer_target(color,x,y)
                if target is None:continue
                choice=attempt(color,target,'staging',(.08,.05,.12),(0.,math.pi/2,-math.pi/2,math.pi))
                staged.add((color,x,y))
                if choice:break
        if not choice and getattr(program.planner,'allow_goal_blocker_staging',False):
            blockers=sorted((c for c in scene if c not in remaining),key=lambda c:min(np.linalg.norm(program.planner.world(scene[c])[:2]-program.planner.world(scene[other])[:2]) for other in remaining))
            for color in blockers:
                for x,y in buffers:
                    target=buffer_target(color,x,y)
                    if target is None:continue
                    choice=attempt(color,target,'staging',(.08,.05,.12),(0.,math.pi/2,-math.pi/2,math.pi))
                    staged.add((color,x,y))
                    if choice:break
                if choice:break
        if not choice:raise ResetBlocked('No audited final delivery or clear tabletop staging transfer exists')
        commit(choice);stage_count+=1
    save(output/'planning-sequence.json',sequence)
    save(output/'planning-scope.json',dict(complete_future_program=not remaining,
         first_leg_only=first_leg_only,remaining_colors=remaining))
    return sequence
