# Kinex × BluPe

User invocation, November 12, 2026: “Acutally lets do this, lets just launch it and see what happens. Lets use the harness and make a new website”. Prior discussion selected Astra through Codex with Kinex robotics tools. This invokes [the shared contract](docs/BLUPE-HARNESS-CONTRACT.md); [the working checklist](docs/COMPLETION-CHECKLIST.md) determines acceptance.

Website: https://kinex-blupe.andlyu.chatgpt.site . Website source: https://github.com/andlyu/blupe-kinex . **Physical acceptance is pending.**

This is an authentic Kinex core/MCP integration, using official plugin snapshot f68a8d7f1ddcae2b096f171b817c232d8730f3ec and Codex 0.162.1. The native Kinex device/servo tools execute through a whole-buffer driver into the shared lease-aware RunnerController and canonical Session API. Kinex generates its motion references; the bridge resamples to the deployed 10 Hz transport and validates all original and generated samples, calibrated joint limits, pacing, reported-contact rejection, gripper bounds, preservation and budgets. Only one actuator buffer may own the gateway. Raw write acknowledges actual transport acceptance; measured completion remains separate.

The public website exposes a bounded tool catalog: device, devices, servo and device_stop. Arbitrary Python, shell, onboarding/profile edits, Cartesian kinematics and superseding/concurrent buffers are not exposed in this first version. This is a stationary YAM adaptation, not the standalone Pi agent, ROS 2 support claim, or demonstrated pick-and-place system. Numerical FK/contact checks are not a simulator rollout.

The planning/vision model remains `gpt-6-astra` with low reasoning through the existing Codex login. Requested and unresolved immutable model IDs are recorded separately from Model=Kinex. Human identity is separate from execution mode. The runner's confirmed email stays out of public source and public snapshots.

## Required preflight

From the shared checkout:

```sh
PYTHONPATH=codex-runner/src codex-runner/.venv/bin/python codex-runner/integrations/kinex/preflight.py --upstream output/kinex-upstream --output codex-runner/integrations/kinex/docs/evidence/preflight.json
```

It exercises the real buffer parser/generator, complete canonical HTTP serializer and validator with a wire spy, and the actual upstream Kinex MCP lifecycle/clock/tools. It sends zero physical commands. The outbound worker refuses missing/stale source-hash-bound receipts. After code changes rerun preflight.

## Launch

Build upstream from its pinned Git revision using `npm ci --ignore-scripts` and `npm run build`. Retain the checkout and dependencies; do not change global Codex or copy login credentials. Use the existing Python environment with numpy/scipy/Pillow/MuJoCo/websocket-client. The launcher needs normal write access to Codex session storage.

```sh
codex-runner/.venv/bin/python codex-runner/integrations/kinex/agent.py --site https://kinex-blupe.andlyu.chatgpt.site --token-file /private/path/runner-token --upstream /absolute/path/kinex-plugins --state /private/path/kinex-state --preflight codex-runner/integrations/kinex/docs/evidence/preflight.json
```

The worker polls outbound HTTPS, claims each website request once, then uses the normal BluPe queue. No claimed/unknown physical request is automatically retried. Stop is polled independently of model inference and sent to the gateway and owned model/runtime processes. The website retains each run's public status; physical footage is resolved through the existing public recording system.

Local collision-model limitation: the inherited canonical XML is a visual/FK model whose robot geoms have contype=0 and conaffinity=0. Its contact counter cannot establish arm-collision protection. The rejection branch is tested with an explicit injected contact fault; no geometry or safety masks are altered in production. Existing gateway workspace/safety checks remain enabled. No physical safety or task acceptance is inferred from these offline tests.

Release safety state: the offline preflight is passed; `physical_command_contract` remains `pending_station_safety_calibration_review`. The outbound worker refuses hardware readiness until that required coverage is verified. A later station reconnection alone cannot enable Run. Runtime fingerprints include source/runtime files and exclude derived Python bytecode caches, which native tool imports may create.

Current selected station: Robo-house YAM (`robot-ba8413962083809c`) by explicit user request. Launch with `--robot-id robot-ba8413962083809c`. See the latest checklist continuation and preflight-robohouse.json for the verified canonical local guard, calibration binding and endpoint regression. The YAM1 pending gate is preserved.
