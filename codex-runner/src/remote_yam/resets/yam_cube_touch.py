"""Narrow allowance for initially touching, nonpenetrating source cubes.

Robot contacts are never handled here. Expected source contacts may persist
while a selected cube lifts away; after separation they cannot recur. Unhandled
neighbors must retain their initial corners within1mm, including after contact
ends, so pushing a neighboring source cannot silently pass.
"""
from __future__ import annotations
import itertools
import numpy as np
from .yam_cube_scenes import box_separation,rotation
from .yam_cube_sizes import edge_m


def scene_boxes(scene,spacing):
    boxes={}
    for color,row in scene.items():
        center=np.array(row['visible_top_center_by_arm']['left']['top_center_m'],float)
        edge=edge_m(row)
        center[1]+=spacing/2;center[2]=row['visible_top_center_by_arm']['left']['support_point_m'][2]+edge/2
        boxes[color]=dict(center=center,rotation=rotation(row['yaw_rad']),half_size=np.full(3,edge/2))
    return boxes


def corners(box):
    signs=np.asarray(list(itertools.product((-1.,1.),repeat=3)))
    return box['center']+(signs*box['half_size'])@box['rotation'].T


class InitialTouchAllowance:
    def __init__(self,boxes,*,penetration_tolerance_m=1e-6):
        self.tolerance=penetration_tolerance_m
        self.initial={c:corners(b) for c,b in boxes.items()}
        self.expected=set();self.active=set();self.handled=set();self.violations={}
        self.contacts={};self.max_corner_motion={c:0. for c in boxes}
        for a,b in itertools.combinations(boxes,2):
            gap=self.gap(boxes[a],boxes[b])
            if gap < -1e-9:raise ValueError('Initial cube penetration: '+a+'/'+b)
            if gap<=1e-8:self.expected.add(tuple(sorted((a,b))))
        self.active=set(self.expected)
        self.monitored={c for pair in self.expected for c in pair}

    @staticmethod
    def gap(a,b):
        return box_separation(a['center'],a['rotation'],a['half_size'],b['center'],b['rotation'],b['half_size'])

    def update(self,boxes,*,selected=None):
        if selected is not None:self.handled.add(selected)
        for color in self.monitored-self.handled:
            displacement=float(np.max(np.linalg.norm(corners(boxes[color])-self.initial[color],axis=1)))
            self.max_corner_motion[color]=max(self.max_corner_motion[color],displacement)
            if displacement>.001:
                self.violations[color]='An unhandled source moved more than1mm'
        for a,b in tuple(self.active):
            if self.gap(boxes[a],boxes[b])>.0002:self.active.remove((a,b))

    def allows(self,a,b,distance_m,*,force_N=0.):
        key=tuple(sorted((a,b)))
        if key not in self.active or distance_m < -self.tolerance:
            return False
        if self.violations:return False
        prior=self.contacts.setdefault('/'.join(key),dict(samples=0,max_force_N=0.,minimum_distance_m=0.))
        prior['samples']+=1;prior['max_force_N']=max(prior['max_force_N'],float(force_N))
        prior['minimum_distance_m']=min(prior['minimum_distance_m'],float(distance_m))
        return True

    def verdict(self):
        return dict(passed=not self.violations,initial_pairs=sorted(self.expected),
                    separated_pairs=sorted(self.expected-self.active),violations=self.violations,
                    max_unhandled_corner_motion_m=self.max_corner_motion,
                    allowed_contact_evidence=self.contacts,
                    penetration_tolerance_m=self.tolerance,separation_threshold_m=.0002,
                    unhandled_corner_motion_limit_m=.001)
