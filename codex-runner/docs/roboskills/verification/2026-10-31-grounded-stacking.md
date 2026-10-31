# Grounded stacking repair — in progress

Task: fix the actual user request “Stack the purple block on the orange block” on YAM-1 through the normal public Site. Invoked BluPe authorization-by-use contract; no operator sign-in or repeated physical/publication confirmation. User-confirmed human identity retained. Prior lift-only acceptance is historical.

## Read-only evidence

- Public ApiDepth top probe passed: paired640×360 RGB/metric optical-Z, capture age0.822s. Three-camera stationary preflight passed in2.752s; ages1.827/1.408/0.735s. Camera calibration `9773d518c8d8a2334dd2c61f9e5bff29e3934d810f1fa43c90d411f00b243958`; native joint convention `native_i2rt_updated`, no extra offsets; camera base spacing0.50m; controller guard bounds retain their independent0.70m origin convention.
- All-camera synthetic transform/mask/invalidated-view/changed-calibration tests pass. Full quality warnings remain available; independent physical accuracy is unverified.
- Local runtime files were macOS dataless; repaired environment outside Documents uses Python3.13.2, NumPy2.5.4, MuJoCo3.17.0, pinned official RoboSkills `8a2860234768b4bec981994d1c14fa380a2c8c7f`. No perception algorithm or upstream agent source was replaced.

## Required offline command contract

Actual path: RobotTools.move_to → RoboCurveTrajectory.build → `_trajectory_waypoints` → HttpSessionAPI.submit_trajectory → JSON encode/decode transport spy. No physical commands. Both-arm fractional gripper starts, close0/open1/partial, first/interior/final packets,10Hz cadence/IDs, untouched joints/arms/grippers, malformed/out-of-range/NaN/Inf input and proven-zero-dispatch invalid generation are covered. Cartesian x/y/z/yaw interior moves and envelope/invalid-neighbour cases are exercised. Pitch/roll are held by the existing tool envelope, not advertised as freely adjustable. Numerically legal envelope points may remain IK-unreachable and are rejected locally. No joint primitive is advertised by RobotTools.

Red regression: original command path changed unrequested joint values through a degrees/radians round trip and surfaced an injected `-1.1102230246251565e-16` gripper packet as a generic measured-feedback error before the bridge; new path validates the full packet first, retains the waypoint/field/value, and permits an explicit revised model decision only for proven-not-dispatched local errors. The injected packet is the shared contract's numeric fixture, not an observed new physical failure; do not claim the old generator reproduced that residual. Exact final numeric targets are copied without widening valid ranges. Existing measured tracking corrections and uncertain-motion non-retry remain intact.

Runnable release gate: `PYTHONPATH=codex-runner/src:codex-runner/tests python -m unittest discover -s codex-runner/tests -p 'test_roboskills*.py' -v`. Required dedicated CI installs the pinned official runtime. Broader RGB-D/RoboCurve/trajectory suites and Site worker/route/TypeScript checks also run. Exact source/validator hashes and final command output are added after commit.

## Current acceptance

- [x] Real paired RGB-D delivered, calibration identity retained; object-coordinate API and honest terminal explanations implemented.
- [ ] Command release gate passed at final source revision, required CI result retained.
- [ ] Published deployment exercised through ordinary public UI under the actual runner name/email.
- [ ] Approach, grasp, retained lift, transfer, supported release and withdrawal observed; purple-on-orange stable result independently reviewed.
- [ ] Current run timing measured (15s post-Home and30s after Run minus evidenced initial queue wait).
- [ ] Live/current replay/history, structured task result, Stop and native parked/lease-release verified on this deployment.

No new timing or success exception is inferred. Preserve the earlier owner's fixed historical exceptions and specific original-recording denial.
