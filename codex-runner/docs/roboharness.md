# RoboHarness on BluPe YAM

This is a stationary YAM embodiment adaptation of [RoboHarness paper v1](https://arxiv.org/abs/2610.14018), not a reproduction of its R1Pro simulation benchmark. [Official upstream revision](https://github.com/BinceQu/RoboHarness/tree/d58e2defb25b9167a1ef14ab778995bf9e9de42f) is the research reference; this adapter is implemented in the shared runner.

The public integration website/source is [blupe-roboharness](https://github.com/andlyu/blupe-roboharness). Its deployment, hosting-only bootstrap, live camera controls, model evidence and preserved completion checklist live there. The website is planned at https://roboharness-blupe.andlyu.chatgpt.site. Physical acceptance is pending; do not describe the integration as verified until its checklist is complete.

## Executed method

`RoboHarnessAdapter` runs a planning/vision agent that selects overhead image keypoints, tracks them bidirectionally with Lucas–Kanade optical flow, grounds them using the shared paired RGB-D calibration and invokes bounded geometric tools: touch, line alignment, plane alignment, incremental pose adjustment and gripper control. Arm-base metres/radians and explicit gripper-frame rotation matrices prevent optical-coordinate guessing. Lost tracking, stale depth, mismatched calibration or invalid packet inputs reject before dispatch.

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
