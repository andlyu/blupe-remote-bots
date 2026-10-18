"""Immutable episode edits and procedural Home; no motor imports or commands."""
import json
import math
from pathlib import Path
import numpy as np
from .recorded_replay import JOINTS, GRIPS, HZ, plan
from .replay_data import episode_name


def validate_source(payload):
    episode_name(payload.get('episode'))
    a=np.asarray(payload['actions'],dtype=float);t=np.asarray(payload['times'],dtype=float)
    if a.ndim!=2 or a.shape[1]!=14 or len(a)<2 or t.shape!=(len(a),):raise ValueError('Invalid episode shape')
    if not np.isfinite(a).all() or not np.isfinite(t).all() or np.any(np.diff(t)<=0):raise ValueError('Invalid episode positions/times')
    if t[-1]-t[0]>300 or np.any(a[:,GRIPS]<0) or np.any(a[:,GRIPS]>1):raise ValueError('Invalid episode duration/grippers')
    return a,t-t[0]


def validate_edit(payload,edit):
    a,t=validate_source(payload)
    if not isinstance(edit,dict):raise ValueError('Expected edit recipe')
    start,end,speed=(edit.get(k) for k in ('start_s','end_s','speed'))
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (start,end,speed)):
        raise ValueError('Crop times and speed must be finite numbers')
    if not 0<=start<end<=t[-1]+1e-8 or end-start<.1:raise ValueError('Keep at least0.1seconds within the source episode')
    if speed not in (1,2):raise ValueError('Replay speed must be1x or2x')
    if not isinstance(edit.get('return_home'),bool):raise ValueError('Choose whether to return Home')
    return dict(schema='abc-replay-edit-v1',episode=payload['episode'],source_sha256=payload.get('source_sha256'),
                start_s=float(start),end_s=min(float(end),float(t[-1])),speed=float(speed),return_home=edit['return_home'])


def suggestions(payload,home):
    a,t=validate_source(payload)
    # Suggestions only. The operator inspects and saves exact crop boundaries.
    # Ignore small warmup motion: sustained departure >10deg from initial pose.
    distance=np.max(np.abs(a[:,JOINTS]-a[0,JOINTS]),axis=1)
    active=np.flatnonzero(distance>math.radians(10))
    start=max(0,float(t[active[0]])-1) if len(active) else 0.
    # Find the last sustained movement toward calibrated zero, after the far pose.
    d=np.linalg.norm(a[:,JOINTS]-np.asarray(home),axis=1)
    peak=int(np.argmax(d));end=float(t[-1]);window=max(3,int(1/np.median(np.diff(t))))
    for i in range(max(peak+1,len(t)//2),len(t)-window):
        if d[i]-d[i+window]>.4 and d[i+window]<.8*d[i]:
            end=float(t[max(1,i-2)]);break
    if end<=start+.1:start,end=0.,float(t[-1])
    return dict(start_s=start,end_s=end,speed=2.,return_home=True)


def apply_edit(payload,edit,home):
    recipe=validate_edit(payload,edit);a,t=validate_source(payload)
    keep=t[(t>recipe['start_s'])&(t<recipe['end_s'])]
    times=np.r_[recipe['start_s'],keep,recipe['end_s']]
    actions=np.column_stack([np.interp(times,t,a[:,j]) for j in range(14)])
    times=(times-times[0])/recipe['speed']
    home_seconds=0.
    if recipe['return_home']:
        target=np.asarray(home,dtype=float)
        if target.shape!=(12,) or not np.isfinite(target).all():raise ValueError('Invalid calibrated Home')
        start=actions[-1].copy()
        ticks=max(30,math.ceil(1.875*float(np.max(np.abs(start[JOINTS]-target)))/.20*10))
        u=np.arange(1,ticks+1)/ticks;blend=10*u**3-15*u**4+6*u**5
        tail=np.repeat(start[None,:],ticks,axis=0)
        tail[:,JOINTS]=start[JOINTS]+blend[:,None]*(target-start[JOINTS])
        actions=np.vstack((actions,tail));times=np.r_[times,times[-1]+np.arange(1,ticks+1)/10]
        home_seconds=ticks/10
    result=dict(payload,actions=actions.tolist(),times=times.tolist(),edit_recipe=recipe,
                generated_home_seconds=home_seconds,derived_replay=True)
    return result


def preview(payload,edit,home):
    derived=apply_edit(payload,edit,home);points=plan(derived)
    return dict(recipe=derived['edit_recipe'],actions=points.tolist(),times=(np.arange(len(points))/HZ).tolist(),
                seconds=len(points)/HZ,source_seconds=float(validate_source(payload)[1][-1]),
                retained_source_seconds=edit['end_s']-edit['start_s'],generated_home_seconds=derived['generated_home_seconds'],
                max_joint_velocity_rad_s=float(np.max(np.abs(np.diff(points[:,JOINTS],axis=0)))*HZ),
                includes_start_approach=False,source_sha256=payload.get('source_sha256'))


class EditorStore:
    def __init__(self,root,model_path):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.model_path=Path(model_path);self.model=json.loads(self.model_path.read_text())
        self.home=self.model['home_target'];self.calibration_id=self.model['calibration_id']
    def _path(self,episode,suffix):return self.root/(episode_name(episode)+suffix)
    def source(self,episode):
        p=self._path(episode,'.source.json')
        return json.loads(p.read_text()) if p.exists() else None
    def put_source(self,payload):
        validate_source(payload)
        if payload.get('derived_replay') or payload.get('edit_recipe'):raise ValueError('Editor requires original command data')
        p=self._path(payload['episode'],'.source.json');old=self.source(payload['episode'])
        if old and old.get('source_sha256')!=payload.get('source_sha256'):raise ValueError('Original episode hash changed')
        self._write(p,payload)
    def recipe(self,episode):
        p=self._path(episode,'.edit.json')
        if not p.exists():return None
        r=json.loads(p.read_text());source=self.source(episode)
        if source is None or source.get('source_sha256')!=r.get('source_sha256'):raise ValueError('Edit no longer matches the source')
        if r.get('calibration_id')!=self.calibration_id:raise ValueError('Edit calibration changed')
        return dict(validate_edit(source,r),calibration_id=self.calibration_id)
    def save(self,episode,edit):
        source=self.source(episode)
        if source is None:raise ValueError('Load original episode first')
        recipe=validate_edit(source,edit);recipe['calibration_id']=self.calibration_id
        self._write(self._path(episode,'.edit.json'),recipe)
        return recipe
    @staticmethod
    def _write(path,doc):
        temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(doc,allow_nan=False));temp.replace(path)
