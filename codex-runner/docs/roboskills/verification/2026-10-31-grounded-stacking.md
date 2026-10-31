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

## First normal-UI depth test (v14) — not task-qualified

Run `f7b751b7a15240a8a71e5d88206104ea`, session `sess_2f38b0586460446c`, episode `ep_1e5353fabe6347ec`, actual Andrew Lyubovsky, exact user stacking instruction. One17-waypoint approach packet completed; right fingertip `[.318825,.021695,.119741]m`, position error1.724mm. No grasp/stack. Agent reported failure; public result/replay retain the explanation. Native status independently verified parked=true,torque_off_verified=true,auto_queue_enabled=true. No uncertain motion or automatic replay.

Failure: comparing whole `/calibration` JSON treated live `cameras.*.depth.captured_at`/`available` as changed calibration. The identity and geometry had not changed. A regression runs against the exact7a6bb6b perception source and fails on this live-metadata change; fixed code excludes only those two live delivery fields, retaining identity/geometry/quality/transport checks. Full quality stays in measured results and initial agent context; concise printed representations prevent the4000-character upstream REPL limit from hiding object coordinates. The first run spent two turns printing/localizing before approach and missed the current timing limits; no historical timing exception applies. It remains failed qualification.

The first-move prompt now uses measured pixel queries and begins a reachable above-object approach in the first Python block when observations permit. Multi-step physical manipulation gets a120-second execution window, within the existing runner's native60–600s limits; the15s post-Home and30s queue-adjusted first-motion requirements are unchanged. Final task verification remains open.

## Tool-shape and tracking verification after v15

- Run `899e4cee34eb48308989c58014956edc` completed three matched approach/correction packets, then the agent ended without grasping because it interpreted moving wrist-camera pixels as object displacement. Camera refresh/calibration pinning worked. The point-list type and moving-camera semantics were made explicit.
- Run `2a97205b588f40b089ca4a420bc264f4` received a valid wrist depth sample but the optional arm argument changed the result schema; the agent checked the plural key and incorrectly concluded depth was absent. Primary `points_base_m` now remains an arm→[x,y,z] mapping for single-arm calls, with the singular alias retained. Exact old-source regression fails, new source passes. Both runs remain failed qualification; no historical exception is inferred.
- v16 source189f083dff565d6624370abda82ff7aef44a8027 clears prior run progress immediately on new submission. Source/perception fix merged inPR181 (`d0124e509ca5f2828b45d78a3d12d30c48702292`), all six push/PR CI checks passed at80a61e.
- v16 run `3e3c56a9d77d486086aa8e13b5d61d69` used real depth and a one-turn six-line approach program. Three matched completed packets produced4.64/5.56/4.99mm errors; original3mm threshold correctly failed the move and latched termination, with no grasp or task-success claim. No workspace replacement or safety-limit rejection occurred. First-motion timing still requires retained-frame review; no success inferred from the UI moving stage.

## Bounded feedback repair — physical qualification pending

The retained command/feedback fixture is `tests/fixtures/roboskills-approach-tracking.json`, projected through canonical FK from actual measured joints. It records3completed samples with a signed error crossing on Y and later Z. The former full residual accumulation crossed back across the target. A bounded false-position update uses an observed bracket instead; otherwise the existing residual step remains. At most4packets per move (initial plus3corrections) can be sent, each only after matched measured completion; per-axis correction remains≤8mm, requested-pose tolerance3mm, and all canonical IK/workspace/pacing/serializer/gateway/lease/Stop checks remain. Failed/unknown packets still end the episode without retry. No motor gains or hardware bounds change.

A gripper-only request now verifies that command's completion without inventing an additional Cartesian pose target. Unrequested joint commands remain byte-for-byte measured values, pose drift is still reported, and every requested Cartesian arm still needs3mm accuracy. A real grasp may change measured contact-loaded pose; that observation is not falsely classified as an unrequested pose-target failure.

Both regressions fail on the old code. The measured-sample interpolator in the offline regression is a model, not physical ground truth or a qualification claim. A new normal-UI loose-purple-on-loose-orange task must verify the physical sequence and result. Previous development timing failures remain recorded; the owner's pre-v13 archival exception does not automatically cover these runs.
