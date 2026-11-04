"""Bounded numeric robot-tool schema compatible with the existing model broker.

The broker accepts robot decision records only. This maps its numeric fields to
an explicit allowlist of RoboHarness geometric tools, never code or CLI flags.
"""
import json
import uuid
from .roboharness_control import InputRejected,number

NAMES=('primitive','arm','point_a','point_b','point_c','u','v','axis','x','y','z','rx','ry','rz','gripper')
SCHEMA={'type':'object','additionalProperties':False,'properties':{
    'action':{'type':'string','enum':['move_to','done','give_up']},
    'targets':{'type':'object','additionalProperties':False,'properties':{n:{'type':['number','null']} for n in NAMES},'required':list(NAMES)},
    **{n:{'type':'string'} for n in ('note','summary','reason','hindsight')}},
    'required':['action','targets','note','summary','reason','hindsight']}

INSTRUCTIONS='''You are the planning/vision component of RoboHarness on physical YAM arms.
Use visual keypoints, persistent tracking, measured RGB-D geometry and geometric
constraints. There is no VLA or prewritten task policy. Return only the supplied
JSON robot decision schema. Tools/shell/web are disabled. Three fresh RGB images
are overhead (paired with depth), left wrist and right wrist, in that order.
Only overhead points supply metric depth grounding. Select points only
in OVERHEAD. u/v are normalized 0..1000 from left/top; 1000 is the last pixel.
Keep every unused target field null. arm=0 means left; arm=1 means right.
For action=move_to, primitive selects ONE tool:
1 track_object: select one to three image points, all from this SAME metric image.
  First: point_a=integer 0..15 and normalized u,v. Optionally add point_b with
  normalized pixel coordinates x,y; optionally add point_c with normalized rx,ry.
  In this read-only tool only, x,y and rx,ry are pixel coordinates 0..1000,
  not translation or rotation. IDs must be distinct; point_c requires point_b.
  Keep all other fields null, including arm,z,rz. Prefer one batch for related
  cube/edge/support samples instead of separate model calls for each point.
  Registration and fresh depth measurement send no arm movement. Lost or missing
  depth stays an explicit error; never infer an unmeasured point from its neighbors.
2 touch: arm, point_a, x,y,z. Move the fixed native grasp origin to that tracked scene point plus
  explicit arm-base offset [x,y,z] metres; orientation stays unchanged. If u,v
  are also provided, select/update point_a in this image before resolving touch.
3 align_line: arm, point_a,point_b,axis. Align intrinsic gripper axis (0=x,1=y,2=z)
  with the directed line from point_a to point_b; keep gripper-center position.
4 plane_parallel: arm, point_a,point_b,point_c,axis. Align that gripper axis with
  the scene plane normal, choosing the nearest normal sign; keep center position.
5 adjust_pose: arm,x,y,z,rx,ry,rz. Increment arm-base translation in metres and
  apply arm-base rotation-vector radians. Max 10 cm and 0.5 rad per command.
  Supply all six numeric components, using 0 for unchanged axes. touch likewise
  needs all three numeric offsets; null is only for fields unused by that tool.
6 gripper: arm,gripper. Normalized fraction 0=closed,1=open; joints are held exactly.
For done/give_up all targets must be null. Use summary/reason and hindsight.
These are geometric tools; move_to is only the decision envelope, not proof of
motion. A measured surface point is NOT a safe grasp pose: account for gripper
approach direction, object dimensions, finger clearance and surface clearance.
Review all camera views, measured poses and tracking/depth warnings. The pose
rotation matrix gives the actual fixed grasp-frame axes in the selected arm base:
tool+Z is finger approach, tool-Y is jaw opening. The target is the native
installed grasp_site, not the palm/camera or exact distal fingertip ends. Do not
shift this API/calibration origin. tool_geometry_reference and nominal_tool_pose
provide nominal installed-reference CAD bounds and pad positions; distal tips
extend about 10 mm along tool+Z beyond the origin. These are reference geometry,
not measured contact/force or a live calibration/collision certificate. For a
local reference point v, base position is grasp_position + R@v. Before closing,
check pad-side overlap and complete finger/body clearance against fresh object
and support measurements, including calibration uncertainty; closing above an
object is an empty grasp. Jaw gap is only nominal, not force or verified contact.
Keep scene features visible; a safe measured-pose inspection/retreat may restore
visibility before re-grounding lost points. Never guess occluded object geometry.
Stay inside existing YAM workspace/limits; unsupported mobile-base/torso actions
are unavailable. Plan short, useful bounded task motion promptly after Home.
Observe after every motion. Verify grasp retention, lift, transfer, release and
stable object placement after withdrawal before reporting success. Never infer
object contact or task success from a completed packet alone. If depth, tracking
or calibration is missing, do not invent geometry. Give up when safe geometry is
unavailable. A local rejected input sent no movement and may be revised from new
state; a timeout, unknown dispatch or safety stop must never be automatically retried.
'''


def instructions_for_camera(camera):
    if camera not in ('top','left','right'):raise InputRejected('Select a registered grounding camera')
    if camera=='top':return INSTRUCTIONS
    label=camera.upper()+' WRIST'
    return INSTRUCTIONS.replace(
        'are overhead (paired with depth), left wrist and right wrist, in that order.\n'
        'Only overhead points supply metric depth grounding. Select points only\n'
        'in OVERHEAD.',
        'are overhead, left wrist and right wrist, in that order.\n'
        'Only '+label+' is paired with metric depth. Select points only in '+label+'.\n'
        'Wrist projection uses current measured settled FK and the registered mounting transform.\n'
        'The other two images provide RGB context, not metric samples.')


def integer(v,label,low,high):
    value=number(v,label,low,high)
    if not value.is_integer():raise InputRejected(label+' must be an integer')
    return int(value)


def decision_response(result):
    if not isinstance(result,dict) or set(result)!=set(SCHEMA['required']):raise InputRejected('Malformed RoboHarness decision')
    if any(not isinstance(result[k],str) for k in ('note','summary','reason','hindsight')):raise InputRejected('Decision text must be strings')
    raw=result['targets']
    if not isinstance(raw,dict) or set(raw)!=set(NAMES):raise InputRejected('Decision needs every named numeric field')
    args={k:v for k,v in raw.items() if v is not None}
    if result['action'] in ('done','give_up'):
        if args:raise InputRejected('Terminal decisions cannot contain motion targets')
        key='summary' if result['action']=='done' else 'reason'
        name=result['action'];arguments={key:result[key],'hindsight':result['hindsight']}
    elif result['action']=='move_to':
        primitive=integer(args.pop('primitive',None),'primitive',1,6)
        names={1:'track_object',2:'touch',3:'align_line',4:'plane_parallel',5:'adjust_pose',6:'gripper'}
        name=names[primitive];arguments={}
        if primitive!=1:arguments['arm']=('left','right')[integer(args.pop('arm',None),'arm',0,1)]
        if primitive in (1,2,3,4):
            count=3 if primitive==4 else 2 if primitive==3 else 1
            ids=['point_'+str(integer(args.pop(k,None),k,0,15)) for k in ('point_a','point_b','point_c')[:count]]
            arguments['point_ids']=ids
        if primitive==1:
            first={'point_id':ids[0],'u':number(args.pop('u',None),'u',0,1000),
                   'v':number(args.pop('v',None),'v',0,1000)}
            if 'point_b' in args or 'point_c' in args:
                registrations=[first]
                for key,horizontal,vertical in (('point_b','x','y'),('point_c','rx','ry')):
                    if key=='point_c' and key not in args:break
                    point_id='point_'+str(integer(args.pop(key,None),key,0,15))
                    if point_id in ids:raise InputRejected('Inspection point IDs must be distinct')
                    ids.append(point_id)
                    registrations.append({'point_id':point_id,
                        'u':number(args.pop(horizontal,None),horizontal,0,1000),
                        'v':number(args.pop(vertical,None),vertical,0,1000)})
                arguments['registrations']=registrations
            else:arguments['register']={'u':first['u'],'v':first['v']}
        elif primitive==2 and ('u' in args or 'v' in args):
            arguments['register']={'u':number(args.pop('u',None),'u',0,1000),'v':number(args.pop('v',None),'v',0,1000)}
        if primitive in (2,5):arguments['offset_m' if primitive==2 else 'delta_m']=[number(args.pop(k,None),k) for k in ('x','y','z')]
        if primitive==5:arguments['rotation_vector_rad']=[number(args.pop(k,None),k) for k in ('rx','ry','rz')]
        if primitive in (3,4):arguments['axis']=('x','y','z')[integer(args.pop('axis',None),'axis',0,2)]
        if primitive==6:arguments['value']=number(args.pop('gripper',None),'gripper',0,1)
        if args:raise InputRejected('Unused tool fields must be null: '+','.join(args))
        arguments['note']=result['note']
    else:raise InputRejected('Unknown RoboHarness action')
    return {'output':[{'type':'function_call','call_id':'roboharness_'+uuid.uuid4().hex,
                       'name':name,'arguments':json.dumps(arguments,allow_nan=False)}]}
