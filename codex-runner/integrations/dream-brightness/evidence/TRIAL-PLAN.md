# Dream1 brightness pilot

Registered before model/physical trials. User requested Dream1 with images50%darker, an adjustable local UI, fixed-per-run brightness and relative performance. Confirmed runner: Andrew; private confirmed email retained only in operational UI/private scope.

- Station: Robo-house YAM, robot-ba8413962083809c, both arms available through normal queue.
- Model: existing selected Dream-1 beta, dreamlabs/dream-1-beta, SDK/client1.0.0. No model substitution or automatic protocol retry.
- Same prompt for both trials: "Pick up the green pen and put it in the cup, then withdraw your gripper and hold."
- Conditions/order:100%baseline, then50%brightness;60seconds maximum each. Restore/verify the starting scene before the second trial. If the scene cannot be restored, report the mismatch and do not call it a controlled pair.
- Primary observed outcome: green pen retained during lift, transferred, released into cup and still in cup after gripper withdrawal by the run deadline. Review physical footage. Runner status/model self-report alone does not establish success.
- Secondary evidence: actual first motion/startup timing, inference count/latency, execution errors and interventions. Report raw counts and differences. One trial per condition is a descriptive pilot; no statistical success-rate claim.
- An infrastructure/model readiness failure without a completed policy test is not evidence of image robustness and is not counted as a human-scored task failure.
- Stop on native safety stop, uncertain/timed-out movement or tool denial. Do not retry a timed-out movement automatically. Retain errors and normal Stop/parking/lease release evidence.
- Record normal UI Run click, Home/readiness, observed actual motion, queue entry/admission, native recordings/replay and review labels. Retain full wall times; exclude only evidenced queue-admission wait. No provisioning exemption is assumed.

The existing controller auto-queue reports stopped/ready; observation currently reports hardware_not_initialized while DISABLED. Normal queue admission owns initialization/Home. No direct hardware initialization or safety bypass is requested.

## Before second condition — 2026-11-04T23:01:44.392151+00:00

Baseline ran physically and the reviewed replay showed a grasp/lift but no release/withdrawal into the cup before the60s deadline. The station returned to its normal parked/off state. Another session then acquired the shared station. Current live view shows the green pen on the table at a different position from the baseline start. The planned50%run may proceed only through the normal FIFO, without interrupting that session. Treat these first two trials as exploratory observed outcomes; their starting-scene difference prevents attributing a performance difference solely to brightness. The matched-scene acceptance requirement remains open. No outcome/threshold was changed to create a success.
