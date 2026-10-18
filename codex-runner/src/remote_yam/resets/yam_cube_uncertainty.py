"""Reproducible offline errors hidden from a frozen cube planner.

Only the physical reset is perturbed. Neither the estimated scene nor the
immutable goals are rewritten. Sampling rejects penetrating initial layouts;
the rejection count and conditional distribution are retained in each receipt.
"""
from __future__ import annotations
from .station import resource

import hashlib
import itertools
import json
import math
import importlib.util
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from .yam_cube_scenes import COLORS, box_separation
from .yam_cube_touch import scene_boxes


def position_error_receipt(scene, spacing, offsets):
    if set(offsets) != set(COLORS):
        raise ValueError('Hidden position offsets must name all three cubes')
    boxes = scene_boxes(scene, spacing)
    estimated = {color: box['center'].copy() for color, box in boxes.items()}
    checked = {}
    for color in COLORS:
        delta = np.asarray(offsets[color], dtype=float)
        if delta.shape != (2,) or not np.isfinite(delta).all():
            raise ValueError('Hidden position offsets must be finite XY metres')
        checked[color] = delta.tolist()
        boxes[color]['center'][:2] += delta
    separations = []
    for a, b in itertools.combinations(COLORS, 2):
        x, y = boxes[a], boxes[b]
        gap = box_separation(x['center'], x['rotation'], x['half_size'],
                             y['center'], y['rotation'], y['half_size'])
        if gap < -1e-9:
            raise ValueError('Hidden error causes initial cube penetration: ' + a + '/' + b)
        separations.append(dict(colors=[a, b], separation_m=gap))
    return dict(
        frame='planner_world', applied_at='physics reset only',
        offsets_world_xy_m=checked,
        max_offset_m=max(float(np.linalg.norm(delta)) for delta in checked.values()),
        estimated_centers_world_m={c: p.tolist() for c, p in estimated.items()},
        true_reset_centers_world_m={c: b['center'].tolist() for c, b in boxes.items()},
        planner_scene_sha256=hashlib.sha256(json.dumps(scene, sort_keys=True).encode()).hexdigest(),
        pairs=separations, planner_estimate_changed=False,
        object_pose_writes_after_reset=0,
    )


def position_trials(scene, spacing, *, radius_m=.010, seed=20261018,
                    random_trials=2, boundary_directions=4):
    """Nominal control, common boundary offsets and independent hidden errors.

    The bound is Euclidean XY radius, not +/-radius on both axes. Common
    offsets preserve touching pairs/clusters. Independent trials alternate
    uniform-area disk samples and exact-radius samples, conditioned on no
    initial penetration. Every rejected sample is counted; nothing is clipped.
    """
    if not math.isfinite(radius_m) or radius_m < 0:
        raise ValueError('Position error radius must be finite and nonnegative')
    if random_trials < 0 or boundary_directions < 0:
        raise ValueError('Trial counts must be nonnegative')
    rng = np.random.default_rng(seed)
    trials = []

    def add(name, offsets, distribution, rejected=0):
        receipt = position_error_receipt(scene, spacing, offsets)
        if receipt['max_offset_m'] > radius_m + 1e-12:
            raise ValueError('Generated offset exceeds the requested radius')
        trials.append(dict(id=name, seed=seed, radius_m=radius_m,
                           distribution=distribution, rejected_initial_samples=rejected,
                           **receipt))

    add('nominal', {c: [0., 0.] for c in COLORS}, 'nominal control')
    if radius_m == 0:
        return trials
    for index in range(boundary_directions):
        angle = 2 * math.pi * index / boundary_directions
        delta = [radius_m * math.cos(angle), radius_m * math.sin(angle)]
        add(f'common-boundary-{index + 1:02d}', {c: delta for c in COLORS},
            'common translation at exact radius; preserves source contacts')
    for index in range(random_trials):
        boundary = bool(index % 2)
        for rejected in range(10000):
            angles = rng.uniform(-math.pi, math.pi, 3)
            radii = np.full(3, radius_m) if boundary else radius_m * np.sqrt(rng.random(3))
            values = radii[:, None] * np.column_stack([np.cos(angles), np.sin(angles)])
            offsets = {c: values[i].tolist() for i, c in enumerate(COLORS)}
            try:
                position_error_receipt(scene, spacing, offsets)
            except ValueError as exc:
                if 'initial cube penetration' not in str(exc):
                    raise
                continue
            add(f'independent-{index + 1:02d}', offsets,
                ('independent exact-radius directions' if boundary else
                 'independent uniform-area disks') + '; conditioned on nonpenetration', rejected)
            break
        else:
            raise ValueError('Could not sample a physically valid hidden-error trial')
    return trials


def pickup_verdict(physics, carry_evidence):
    """Use the existing carry/contact criteria, without claiming goal success."""
    touch = physics['initial_object_touch']
    carried = bool(carry_evidence and carry_evidence[-1]['stage'] == 'lift'
                   and carry_evidence[-1]['passed'])
    return dict(passed=bool(carried and not physics['unexpected_contacts_max_N']
                            and (touch is None or touch['passed'])),
                scope='first pickup only; transfer/release/goals untested',
                carried=carried, carry_evidence=carry_evidence,
                unexpected_contacts_max_N=physics['unexpected_contacts_max_N'],
                initial_object_touch=touch, full_task_passed=False)


_ENVELOPE_AUDITORS = {}


def add_inactive_arm_clearance(tree, active_side, clearance_m):
    """Planning-only contact margin for the parked arm, after nominal audit.

    A measured simulation contact at a nominally clear cross-arm descent
    motivates2mm reserve. This model never drives or grades the physics run.
    """
    if not math.isfinite(clearance_m) or clearance_m<0:
        raise ValueError('Inactive arm clearance must be finite and nonnegative')
    if active_side not in ('left','right'):raise ValueError('Unknown active arm')
    if not clearance_m:return []
    other='right' if active_side=='left' else 'left'
    changed=[]
    for geom in tree.findall(f".//body[@name='{other}_link1']//geom"):
        geom.set('margin',str(max(clearance_m,float(geom.get('margin','0')))))
        changed.append(geom.get('name',geom.get('mesh')))
    return changed


def audit_planning_envelope(runtime_root, folder, parts, uncertainty_m, *, inactive_arm_clearance_m=0.):
    """Additional robot clearance audit; never replaces the nominal CAD audit.

    Inflate XY half extents, retaining real cube Z, mass and closure. Overlapping
    *uncertainty volumes* of touching cubes do not imply physical penetration:
    cube/cube contacts and selected-pad contact remain owned by the unchanged
    nominal audit and by actual perturbed contact dynamics. Their exclusions
    here apply only to this additional conservative robot-clearance model.
    """
    import contextlib
    import io
    from .yam_cube_program import save
    root, folder = Path(runtime_root), Path(folder)
    path = Path(resource('auditor'))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest not in _ENVELOPE_AUDITORS:
        spec = importlib.util.spec_from_file_location('uncertainty_cad_'+digest[:12], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ENVELOPE_AUDITORS[digest] = module
    module = _ENVELOPE_AUDITORS[digest]
    compile_nominal = module.compile_model
    plan = json.loads((folder/'result.json').read_text())['plans'][0]
    selected, side = plan['color'], plan['arm']
    model_hashes = []
    margin_geoms = []

    def compile_inflated(xml, *, reuse=False):
        tree = ET.fromstring(xml)
        contact = tree.find('contact')
        for color in COLORS:
            geom = tree.find(f".//geom[@name='cube_{color}']")
            half=np.fromstring(geom.get('size'),sep=' ')
            half[:2]+=uncertainty_m
            geom.set('size',' '.join(map(str,half)))
        for a, b in itertools.combinations(COLORS, 2):
            ET.SubElement(contact, 'exclude', body1='cube_'+a, body2='cube_'+b)
        for finger in ('tip_left','tip_right'):
            ET.SubElement(contact, 'exclude', body1='cube_'+selected,
                          body2=side+'_installed_'+finger)
        margin_geoms.extend(add_inactive_arm_clearance(tree,side,inactive_arm_clearance_m))
        model_xml = ET.tostring(tree, encoding='unicode')
        model_hashes.append(hashlib.sha256(model_xml.encode()).hexdigest())
        return compile_nominal(model_xml, reuse=reuse)

    output = folder/'uncertainty-audit.json'
    argv = ['--runtime-root',str(root),'--preview',str(folder),'--parts',str(parts),
            '--output',str(output),'--reuse-model','--stop-on-failure']
    if (folder/'planning-targets.json').exists():
        argv.append('--allow-staging')
    stream = io.StringIO()
    module.compile_model = compile_inflated
    try:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = module.main(argv)
    finally:
        module.compile_model = compile_nominal
    result = json.loads(output.read_text())
    result.update(scope='Additional inflated XY robot clearance only; nominal contact audit and perturbed physics still required',
                  position_uncertainty_xy_m=uncertainty_m, physical_cube_edges_m={c:float(json.loads((folder/'planning-scene.json').read_text())[c].get('declared_height_m',.030)) for c in COLORS},
                  inactive_arm_planning_clearance_m=inactive_arm_clearance_m,
                  inactive_arm_margin_geoms=sorted(set(margin_geoms)),
                  clearance_envelope_edges_xy_m={c:float(json.loads((folder/'planning-scene.json').read_text())[c].get('declared_height_m',.030))+2*uncertainty_m for c in COLORS},
                  excludes_only_in_additional_model=['cube/cube uncertainty-volume intersections','selected cube/active grasp pads'],
                  wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  compiled_envelope_xml_sha256=model_hashes)
    save(output, result)
    (folder/'uncertainty-audit-command.txt').write_text(stream.getvalue())
    return code == 0, result
