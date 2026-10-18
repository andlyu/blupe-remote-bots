"""Offline scene scheduling around the existing individually audited planner."""
import copy
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import shutil
from types import SimpleNamespace
from .yam_cube_program import save
from .yam_cube_reset import ResetBlocked

_AUDIT_MODULES={}


def run_audit(path,argv):
    """Run the same auditor with a version-bound compiled-model cache.

    Model XML and mesh hashes must still match. Every invocation constructs new
    MjData; no qpos/contact state carries between candidates. Infrastructure
    exceptions propagate. Used only for offline candidate auditing, including
    the live runner's planning phase; this helper never commands hardware.
    """
    path=Path(path);key=hashlib.sha256(path.read_bytes()).hexdigest()
    if key not in _AUDIT_MODULES:
        spec=importlib.util.spec_from_file_location('cube_study_audit_'+key[:12],path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _AUDIT_MODULES[key]=module
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        code=_AUDIT_MODULES[key].main(argv)
    return SimpleNamespace(returncode=code,stdout=stream.getvalue())

def plan_scene(program,state,scene,output):
    """Choose an auditable next cube, retaining every rejected attempt.

    This changes simulation scheduling only. A cube may leave a touching group
    first if another cube cannot yet be grasped. No unchecked plan is selected;
    each future state is an explicit planning hypothesis until dynamics runs.
    """
    output=Path(output);state=copy.deepcopy(state);scene=copy.deepcopy(scene)
    remaining=['blue','orange','yellow'];order=[];attempts=[]
    while remaining:
        choice=None
        def distance(color):
            a=scene[color]['visible_top_center_by_arm']['left']['top_center_m']
            b=program.targets['targets'][color]['visible_top_center_by_arm']['left']['top_center_m']
            return sum((x-y)**2 for x,y in zip(a,b))
        robust=getattr(getattr(program,'args',None),'planning_profile',None)=='robust-v2'
        searches=(((.08,),(0.,1.5707963267948966,-1.5707963267948966,3.141592653589793)),
                  ((.05,.12),tuple(i*3.141592653589793/4 for i in range(-4,4)))) if robust else (
                  (None,(0.,)),(None,(1.5707963267948966,-1.5707963267948966,3.141592653589793)))
        for heights,turns in searches:
          for color in sorted(remaining,key=distance):
            folder=output/f'attempt-{len(attempts)+1:02}-{color}'
            folder.mkdir();program.out=folder
            program.planner.destination_yaw_offsets=turns
            if robust:
                program.planner.destination_grasp_yaws=turns
                program.planner.transfer_height_margins=heights
                program.planner.cache_paths=True
            try:
                plan=program.make_plan(color,scene,state)
            except ResetBlocked as exc:
                attempts.append(dict(color=color,passed=False,error=str(exc)))
                save(output/'scheduling.json',dict(order=order,attempts=attempts))
                continue
            choice=(color,plan,folder)
            break
          if choice is not None:break
        if choice is not None:
            color,plan,folder=choice
            shutil.copytree(folder/(color+'-plan'),output/(color+'-plan'))
            attempts.append(dict(color=color,passed=True))
            order.append(color);remaining.remove(color)
            state['joints']=copy.deepcopy(plan['final_joints'])
            state['left_gripper'],state['right_gripper']=plan['final_grippers']
            released_yaw=scene[color]['yaw_rad']+plan.get('destination_yaw_offset_rad',0.)
            scene[color]=copy.deepcopy(program.targets['targets'][color])
            scene[color]['yaw_rad']=released_yaw
            save(output/'scheduling.json',dict(order=order,attempts=attempts))
        else:
            raise ResetBlocked('No currently remaining cube has a complete audited path: '+','.join(remaining))
    save(output/'planning-order.json',order)
    return order
