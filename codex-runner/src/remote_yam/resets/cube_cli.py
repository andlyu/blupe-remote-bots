#!/usr/bin/env python3
"""Run the three-cube program with the selected native execution policy."""
import argparse,json,signal,sys
from pathlib import Path


def main(argv=None,shared_io=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-root',type=Path,required=True);p.add_argument('--calibration',type=Path,required=True);p.add_argument('--targets',type=Path,required=True);p.add_argument('--parts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--ssh',default=None);p.add_argument('--identity',default=None);p.add_argument('--resume-plan',type=Path);p.add_argument('--resume-audit',type=Path);p.add_argument('--owner-file',type=Path);mode=p.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--sense-only',action='store_true',help='Read current state and cube positions without initializing or moving');p.add_argument('--state',type=Path);p.add_argument('--scene',type=Path)
 p.add_argument('--timing-profile',choices=('native','sim-free','sim-qualified'),help='Qualified default sim-qualified:0.1s free and0.8s contact/carry floors with completion wait; Home stays native. Native preserves all controller ramp timings; sim-free shortens only free moves.')
 p.add_argument('--workspace-config',type=Path,help='Calibrated rectangle used to identify task cubes; does not limit robot collision checks')
 p.add_argument('--accept-late-frames',action='store_true',help='Operator-authorized stationary trial: existing stopped decoder permits5s at receipt; retain distinct observations while arms hold')
 p.add_argument('--execution-policy',choices=('controller-faults','validated'),help='Qualified default: controller-faults continues the planned program through observation/state/geometry warnings, retaining native motor guards and Stop. Legacy default: validated. Requires matching native controller.')
 p.add_argument('--planning-profile',choices=('legacy','qualified','size-aware','pickup-feedback'),default='qualified',help='pickup-feedback enables fresh measured RGB-D pickup IK/replanning and completed-placement corrections; timing is selected separately')
 p.add_argument('--feedback-reference-root',type=Path,help='Optional warm-start initial-scene.json/original-plans.json; fresh RGB-D and full path audits still determine every move')
 p.add_argument('--feedback-close-gap-mm',type=float,default=20.,help='Size-aware close/carry POSITION target in millimeters; blocked contact and native force/current limits remain separate')
 p.add_argument('--feedback-extra-open-gap-mm',type=float,default=20.,help='Additional pregrasp opening beyond projected cube width and10mm clearance;40 gives80mm for30mm cubes')
 p.add_argument('--after-replay',help='Continue only from this completed primary replay in powered Hold; Stop must never trigger automatic relaunch')
 p.add_argument('--home-after-replay',action='store_true',help='Perform exactly one existing native Home before the first fresh cube scene')
 p.add_argument('--staging-feedback',action='store_true',help='Use the existing audited staging scheduler to warm-start fresh pickup feedback')
 p.add_argument('--cube-edges-mm',type=float,nargs=3,metavar=('BLUE','ORANGE','YELLOW'),help='Declared cube edges25..30mm for --planning-profile size-aware; default30mm each')
 a=p.parse_args(argv)
 pickup_feedback=a.planning_profile=='pickup-feedback'
 if a.home_after_replay and not a.after_replay:p.error('--home-after-replay requires --after-replay')
 if a.staging_feedback and not pickup_feedback:p.error('--staging-feedback requires --planning-profile pickup-feedback')
 size_aware=a.planning_profile in ('size-aware','pickup-feedback')
 if a.cube_edges_mm and not size_aware:p.error('--cube-edges-mm requires --planning-profile size-aware')
 if a.cube_edges_mm and any(not 25<=v<=30 for v in a.cube_edges_mm):p.error('Declared cube edges must be25..30mm')
 if size_aware:
  a.requested_planning_profile=a.planning_profile
  a.planning_profile='qualified'
  a.cube_edges_m=dict(zip(('blue','orange','yellow'),[v/1000 for v in (a.cube_edges_mm or [30,30,30])]))
 a.timing_profile=a.timing_profile or ('sim-qualified' if a.planning_profile=='qualified' else 'native')
 a.execution_policy=a.execution_policy or ('controller-faults' if a.planning_profile=='qualified' else 'validated')
 if a.home_after_replay and a.execution_policy!='controller-faults':p.error('--home-after-replay uses the existing controller-faults native Home lifecycle')
 if a.planning_profile=='legacy' and a.execution_policy=='controller-faults':p.error('controller-faults executes a complete qualified program; use --planning-profile qualified or --execution-policy validated for legacy checkpoints')
 if a.resume_plan and not a.resume_audit:p.error('--resume-plan requires --resume-audit')
 if a.resume_plan and a.planning_profile!='legacy':p.error('Legacy checkpoint continuation requires --planning-profile legacy; qualified runs never replay uncertain stages')
 if a.dry_run and not (a.state and a.scene):p.error('--dry-run requires --state and --scene')
 from remote_yam.resets.yam_cube_program import CubeProgram
 a.output.mkdir(parents=True,exist_ok=False)
 def cancel(signum,frame):raise KeyboardInterrupt('Operator cancelled cube program')
 if shared_io is None:signal.signal(signal.SIGTERM,cancel)
 try:
  if pickup_feedback:
   from remote_yam.resets.yam_cube_size_profile import PickupFeedbackCubeProgram
   program=PickupFeedbackCubeProgram(a)
  elif size_aware:
   from remote_yam.resets.yam_cube_size_profile import SizeAwareCubeProgram
   program=SizeAwareCubeProgram(a)
  else:program=CubeProgram(a)
  # Allow measured lateral tracking error during descent, then squeeze1mm.
  # Physical CLI only: simulator callers retain their frozen planner profile.
  if a.planning_profile=='qualified' and not size_aware:
   program.planner.pregrasp_clearance_m=.010
   program.planner.grasp_compression_m=.001
  if a.sense_only:return program.sense_only()
  if a.dry_run:return program.dry_run(json.loads(a.state.read_text()),json.loads(a.scene.read_text()))
  return program.run(io=shared_io) if shared_io is not None else program.run()
 except Exception as exc:
  (a.output/'startup-failure.json').write_text(json.dumps({'state':'startup_failed','error':str(exc),'physical_motion_sent':False},indent=2));print(str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
