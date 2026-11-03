# RoboHarness on BluPe YAM

This is a stationary YAM embodiment adaptation of [RoboHarness paper v1](https://arxiv.org/abs/2610.14018), not a reproduction of its R1Pro simulation benchmark. [Official upstream revision](https://github.com/BinceQu/RoboHarness/tree/d58e2defb25b9167a1ef14ab778995bf9e9de42f) is the research reference; this adapter is implemented in the shared runner.

The public integration website/source is [blupe-roboharness](https://github.com/andlyu/blupe-roboharness). Its deployment, hosting-only bootstrap, live camera controls, model evidence and preserved completion checklist live there. The website is deployed at https://roboharness-blupe.andlyu.chatgpt.site. Physical acceptance is pending; do not describe the integration as verified until its checklist is complete.

## Executed method

`RoboHarnessAdapter` runs a planning/vision agent that selects overhead image keypoints, tracks them bidirectionally with Lucas–Kanade optical flow, grounds them using the shared paired RGB-D calibration and invokes bounded geometric tools: touch, line alignment, plane alignment, incremental pose adjustment and gripper control. All three RGB views inform planning; only the overhead view supplies paired depth for point grounding. Wrist depth is unused and is not transferred. Every source view remains at most two seconds old and must follow the fixed measured settled boundary. Camera acquisition is followed by a fresh measured feedback read under the same lease and cursor; timestamps are never rewritten.

Arm-base metres/radians and explicit gripper-frame rotation matrices prevent optical-coordinate guessing. Lost tracking, stale depth, mismatched calibration or invalid packet inputs reject before dispatch.

The normal subscription model broker accepts a numeric robot decision schema; an explicit allowlist maps that schema to these tools. No model-generated code, URLs or CLI arguments execute. The researcher confirmed Model/approach `RoboHarness` and delegated current compatible planning/vision model selection. Underlying requested model is `gpt-6-astra`, low reasoning; immutable resolved version is explicitly unknown and no fallback exists. Dream1 remains the preference if a VLA role is added; this method has no VLA component.

## Release and runtime checks

Run from a clean published checkout:

```sh
python -m pip install -r codex-runner/requirements-roboharness.txt
PYTHONPATH=codex-runner/src:codex-runner python codex-runner/roboharness_preflight.py --output /tmp/roboharness-preflight.json
```

The required RoboHarness CI job executes the actual decision parser, point tracker, geometric packet generator, canonical Session API validator and JSON serializer with zero hardware dispatch. It covers both arms, normalized gripper endpoints/fractional starts, pacing, held joints, invalid/stale inputs and timeout refusal. A clean passed receipt binds all source, safety profiles, tests and robot-model hashes; startup and each launch reject stale or incomplete receipts. Numerical FK/IK/contact checks are not a dynamics rollout.

The website bootstrap uses `RoboHarnessPlayground`, canonical HostedRunner/MultiRobot fleet, existing queue/lease, measured Home, shared feedback reconciliation, workspace/contact/joint limits, Stop and normal parking. Confirmed human runner name/email are required before queue submission; execution mode and underlying model are separate metadata. Private email never belongs in public evidence.

Exact per-station camera/model calibration IDs are supplied by the hosting configuration. Experimental calibration-quality warnings remain visible and do not establish physical grasp accuracy. The hash-pinned historical controller workspace provides an additional safety envelope; it does not replace the current execution model binding or gateway validation.

No timed-out or uncertain movement is retried automatically. Every physical verification must retain matched lifecycle/Home timestamps and visually observed method onset, plus live/immediate/historical replay evidence, under the integration harness contract.

## Camera-delay regression

The first deployed hover attempt (`ep_d758914999e442e6`) completed normal Home but camera acquisition took 3.598 seconds. Strict feedback freshness rejected the old sample before model inference or a method packet. The sanitized measured Home fixture reproduces that failure against revision a8b94aaa. The repaired path refreshes actual feedback after capture and again before packet construction, and rejects stale or changed-lease refreshes with zero model/actuator dispatch. Camera tests retain the strict two-second age, post-settle boundary, cancellation and calibration checks. The release gate now requires 33 tests and binds the complete shared Python runner inventory. This repair is offline evidence, not a physical-task pass.

The next hover attempt (`ep_086edc7217e040a3`, revision4e36fbb5) executed67 waypoints and reached measured settled completion, then rejected the retreat because the station correctly clears `homed` after leaving Home. The new regression retains the measured post-movement state. Startup Home is still mandatory; non-Home feedback is usable only after exact pending-packet measured completion under the same previously confirmed Home/episode/lease/cursor. Freshness, settled, safety, joint/workspace/contact and timeout guards remain. The35-case gate tests the next real retreat packet and rejects missing Home, mismatched lease/episode/cursor/count and stale/unsafe/unsettled completion. Historical timing and full manipulation/replay acceptance remain pending.
