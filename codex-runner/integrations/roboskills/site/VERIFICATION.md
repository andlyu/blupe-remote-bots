# RoboSkills × BluPe — verified behavior

Timing contract update (October 30, 2026): the shared harness now requires
15 seconds after settled startup Home (or documented no-Home robot readiness)
and 30 seconds after Run/Start excluding evidenced initial queue-admission wait.
Site entry is context only. References below to older timing gates are preserved
historical assessments. The 107.56-second packet-preparation time and approximate
97-second queue/readiness description do not establish a queue-adjusted pass
without matched admission, Home/readiness and visual motion evidence. Current
timing remains unverified; see the maintained checklist. No retest was performed.

Site: https://blupe-bimanual-skills.andlyu.chatgpt.site/
Shared source: https://github.com/andlyu/blupe-remote-bots/tree/main/codex-runner/integrations/roboskills

The live website executes the pinned RoboSkills persistent Python agent through the shared BluPe remote-arms harness. Model is RoboSkills; the current physical planner is gpt-6-sol, configured separately. Normal queue, lease, readiness, IK/workspace/pacing checks, hardware limits, Stop and parking remain intact. Name/email defaults are editable. Public run projections omit private email and capabilities. Viewing cameras, results and replay does not require sign-in; shared compute/control uses the connected operator.

Physical run2ea288ea830e471a86eb6d1d98971c50 completed a20mm paired lift goal, one-second hold and return, with the unchanged3mm Cartesian tolerance. Measured rises17.80/20.97mm, lift errors2.21/0.98mm, return errors2.14/0.08mm; grippers changed less than0.0001. Native status confirmed parked and torque off. Task success is a measured primitive check, not the upstream benchmark's native success score (unset).

[Actual physical replay](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/2ea288ea830e471a86eb6d1d98971c50/assets/physical.mp4) played and seeked through the website; anonymous byte-range access returned206. Completed progress stages and exact earlier measured failure reasons remain visible.

The15-second startup requirement remains unmet: latest Run04:21:30.927Z, first packet prepared04:23:18.484Z,107.56s later, including about97s queue/readiness. Exact visual onset was not separately timed. No GPU or research exception is claimed. The long wait does not alone prove a handoff bug. The backend's legacy public conversation projection labels callers API caller; this website/journal/receipts retain the actual confirmed runner.

Earlier tool review denied publishing the specific original failed-test recording; it remains local and no alternate upload route was used. New authorized tests and their automatic replays worked. This denial is not missing routine motion permission.

The native simulation check generated a real MuJoCo task and Blender replay: demonstration8/8; build rejected robot-rest and scene-framing; frozen-task solver not run. All outputs are reviewable in the website. Full fresh simulation build/solve success is not claimed.

Validation: focused22tests+8subtests passed; broader1621passed,4skipped,254subtests with CI dependencies; Node358passed; TypeScript/production build passed. The accumulated-offset regression failed before its fix and passed after.

See [the complete preserved checklist](docs/COMPLETION-CHECKLIST.md). Timing/full qualification remain open pending evidence or an explicit user exception.
