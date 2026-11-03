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

## Retained public camera clips

An optional `public_replay_root` enables a read-only camera observer after successful normal queue submission. It waits for this exact controller attempt/episode to reach running, captures only the fixed station’s actual overhead JPEG feed at a nominal2Hz, and stops when that execution ends or changes. Frames carry source/received UTC labels. Missing/stale captures are explicit gap frames and mark the clip partial. VFR MP4 timing follows received wall time, without invented scene motion. Encoding runs independently with one FFmpeg thread; no model request, session, Home, actuator command or movement retry is added.

The private-policy-frame loopback guard is unchanged. Temporary camera images are removed after encoding; this separate cache retains only public immutable MP4s and public capture metadata. The existing `IntegrationRuns` reader binds each clip to a station-scoped run receipt, verifies its hash/size and serves byte ranges for seeking. `/api/roboharness/replay-evidence` projects source-frame times and public clip provenance. Unknown/private fields are excluded. Encoder/capture failures remain visible and cannot cancel an already-accepted robot session. Existing normal Jetson/archive recording remains independent. A one-GiB retained-cache ceiling reports failure without deleting older evidence.

The41-case required gate now includes real synthetic-fixture MP4 encoding, immutable byte-range playback, clock/gap metadata, wrong origin/robot/attempt rejection, encoder failure, accepted-session preservation and public timeline privacy. Synthetic test clips are temporary and are never presented as hardware evidence. FFmpeg’s actual version is retained in preflight and clip metadata. Physical playback and object-outcome acceptance still require deployed UI evidence.


Tracking regression after hover-003: the 21px LK window was unstable on the orange block's flat center in nearby recorded camera footage after JPEG/H264 compression. A 41px window includes the block boundary, with the same bidirectional 1.5px consistency gate and loss rejection. The two retained fixture images are actual demo camera data; the later image was decoded from the public clip, not the exact RGB-D rejection frame. Their provenance/limitation is in `tests/fixtures/roboharness-hover003-tracking.json`. The regression also verifies that an occluded block is rejected without reacquisition. Every subsequent tracking update retains its exact top image, source timestamp, calibration and before/after point state in the private capability-free wire recording. This repair requires new physical verification; it does not turn the failed run into a pass.

The replay encoder uses null stdin and `-nostdin`, so running the offline gate from a streamed shell cannot let FFmpeg consume deployment commands.
