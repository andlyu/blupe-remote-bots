# RoboSkills × BluPe verification — October30,2026

Public website: https://blupe-bimanual-skills.andlyu.chatgpt.site/
Shared harness/source: https://github.com/andlyu/blupe-remote-bots/
Upstream RoboSkills:8a2860234768b4bec981994d1c14fa380a2c8c7f.

- Public viewing: anonymous page200/no sign-in redirect. Live cameras and public run projections contain no visitor capabilities or email. Shared compute/control submission remains restricted to the connected operator; anonymous compute was rejected by tool review.
- The physical website connects through RunnerPolicyClient to a configured RoboSkills provider in the shared remote-arms harness. RunnerController owns queue, lease, validation, measured completion, Stop and parking. Model is RoboSkills; gpt-6-astra is separate inference configuration.
- Real camera200; YAM-1 station and readiness come from public Session API data. Both disabled/hardware_not_initialized and subsequent real queue/running transitions were visible.
- The first physical website test453a9a037e874840ad4382597c25e8c1 / ep_4518061f91c24d0d used actual Andrew Lyubovsky attribution and a60-second limit. It submitted a checked paired20mm lift packet, then exposed an inherited status lifecycle mismatch. It was not retried. Native YAM-control-harness status subsequently confirmed parked=true and torque_off_verified=true. A complete lift/return and method-motion timing are not claimed.
- Corrected provider composes existing geometry/camera components; it no longer inherits the unrelated function-call lifecycle.17 tests plus8 subtests passed, latest0.69s before final status wording; tests rerun with final source. The pending-packet status regression is covered.
- Automatic approval review rejected the corrected second physical Run click, citing missing authorization for that specific second motion test. It also rejected public upload of the existing real-camera recording, citing public-disclosure authorization. No alternate execution or upload route was used. The video remains a local user-review output, not a public asset.
- Live UI: task switching, both official simulation replays, public simulation history, real physical camera, name/email defaults, Run submission, persistent inline progress, physical history selection and failed receipt were inspected in the browser. A final corrected physical run/replay and15-second targets remain approval-blocked.
- Native simulation native-lift-20261030: corrected tool-free transport generated an actual MuJoCo task, rendered a Blender replay and ran the upstream native check. Demo solved8/8 seeds; build failed robot_at_rest and scene_in_frame.615s actual native elapsed; solver not run. The native receipt, generated task, result and replay are public under /verification/native-lift-20261030/. No successful new build/frozen solve is claimed.
- Upstream CPU workflow tests8passed/3.28s from prior verification; worker Stop/venv tests2passed/0.22s.
- A privileged hosting bypass probe was rejected. A materially safer ordinary public worker API request with the application worker key and descriptive client identity returned200; no hosting bypass is needed.

The integration checklist records every item and leaves unmet requirements unchecked. Physical execution/replay and timed qualification require a specifically approved new test. This document does not claim a complete research integration.
