# Kinex offline command coverage — November 12, 2026

Release gate: `PYTHONPATH=codex-runner/src codex-runner/.venv/bin/python codex-runner/integrations/kinex/preflight.py --upstream /absolute/path/kinex-plugins --output /private/path/preflight.json`.

The isolated release used the previously published runtime branch as its clean base, with only the Kinex files overlaid. Required result: [preflight-native.json](evidence/preflight-native.json). It records exact source SHA-256 values, upstream Git revision and installed core/setup/MCP fingerprints. Upstream is `f68a8d7f1ddcae2b096f171b817c232d8730f3ec`, Kinex core/setup 1.0.0, Codex 0.162.1. The deployed canonical validator is `remote_yam.session._trajectory_waypoints` plus the full `HttpSessionAPI.submit_trajectory` serializer, whose file hashes are in that receipt. CI and the outbound worker enforce the same preflight; missing/stale receipts disable Run.

The final gate passed 15 Python tests, including one native test containing 124 tool cases. It produced 60 canonical wire-spy packets and 50 rejected cases, with zero physical commands. Python test subprocess: 5.562 s; native lifecycle subprocess: 0.504 s; total preflight parent wall time: 6.444 s. These are synthetic-feedback software checks, not physical motion, model inference or simulation rollouts.

| Primitive / boundary | Actual path and verified scope |
| --- | --- |
| Both six-joint arms | Native device buffers and servo through MCP/core, JSONL driver, production authenticated HTTP bridge, RunnerController and real serializer; absolute radians, serialized degrees; every joint lower/upper endpoint, 1e-12 rad inside and 1e-10 rad outside calibrated/model intersection |
| Both normalized grippers | Native write with 0, 1, 0.37 and near-endpoint interior values; measured starts include 0.9992793312193716 and 0.9947321472782467; exact final endpoints, no negative interpolation residual |
| Packet invariants | Finite first/interior/final samples, contiguous IDs, 10 Hz, <=0.35 rad/s joints and <=1 fraction/s grippers, exact uninstructed arm/gripper preservation; direct tests also cover malformed durations, budgets, NaN/infinity and raw negative residual rejection |
| Read tools | Native reads of both arms/grippers, all three RGB cameras in base64/file modes with real image attachments from explicit 4x3 synthetic fixtures, world clock/wait and concurrent arm reads |
| Local rejection | Invalid targets/malformed joints, stale/unsafe/unhomed/unsettled/wrong-source/wrong-robot feedback and changed lease reject without outbound actuator packets |
| Stop / ownership | Native device_stop reaches local stop spy; separate regressions cover failed Stop, cancellation during a read, no model spawn after cancel, no late-ack success, active-buffer exclusion and full acknowledgement validation |
| Final feedback | Joint agreement and additional 0.02 normalized gripper agreement required; this is not proof of grasp or task outcome |
| Exclusions | Cartesian/IK goals explicitly reject. No arbitrary shell/Python, ROS 2 integration, simultaneous/superseding buffers or demonstrated pick-and-place is advertised |

## Collision-model limitation and retained failure

A probe of 1,000 random in-bounds configurations could not generate a contact. Inspection confirmed that the inherited canonical model's 24 robot/visual geoms have collision masks (0,0), with only the floor at (1,1). The failed probe receipt is retained as [contact-probe-failed.json](evidence/contact-probe-failed.json). No production collision masks or shared model assets were changed. A reported-contact fault is explicitly injected in the native fixture to verify the existing rejection branch; that test does not verify collision geometry. Local predictive collision protection is therefore not established. Existing remote gateway workspace/safety checks remain enabled, and all physical acceptance remains unchecked.

The full command-contract checklist item remains unchecked pending the remaining safety/calibration coverage review; the numeric/native coverage above does not silently certify that broader item. No physical run, onset timing, live moving-arm view, real replay or task success is claimed.

Release safety state: the offline preflight is passed; `physical_command_contract` remains `pending_station_safety_calibration_review`. The outbound worker refuses hardware readiness until that required coverage is verified. A later station reconnection alone cannot enable Run. Runtime fingerprints include source/runtime files and exclude derived Python bytecode caches, which native tool imports may create.
