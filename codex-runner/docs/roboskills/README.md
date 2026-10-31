# RoboSkills on BluPe remote arms

Timing contract update (October 30, 2026): the shared harness now requires
15 seconds after settled startup Home (or documented no-Home robot readiness)
and 30 seconds after Run/Start excluding evidenced initial queue-admission wait.
Site entry is context only. References below to older timing gates are preserved
historical assessments. The 107.56-second packet-preparation time and approximate
97-second queue/readiness description do not establish a queue-adjusted pass
without matched admission, Home/readiness and visual motion evidence. Current
qualification is not newly certified by this contract edit. The later owner-
specific per-Run reassessment and exact receipt below are retained; post-Home
and other-run qualification remain separate. No retest was performed.

The physical provider runs OpenRoboKit's persistent Python agent loop from
`core.agent.run`, pinned to8a2860234768b4bec981994d1c14fa380a2c8c7f.
The model sees actual RGB images, measured state and a small BluPe tool surface:
`bot.status`, `bot.observe`, `bot.move_to`, `bot.wait`, and `finish`.
The Cartesian/IK component and RunnerController retain the station workspace,
queue, lease, packet validation, correlated measured completion and Stop.
This adapter does not expose the complete RoboKit/SAM API or replay simulation
joint targets. Its physical success score is explicitly unscored.

The harness Model is **RoboSkills**; the underlying inference model is separate
configuration (now `gpt-6-sol`; earlier tests used `gpt-6-astra`). Real name/email remain editable before joining.
The public website connects using RunnerPolicyClient's normal visitor, CSRF,
Run/status/Stop protocol. Cameras, progress and retained history are in the site.
The website's separate agentic_sim workflow retains native task checks, generated
code and a clearly labeled simulation replay, including failed checks.

## Run

Use a Python3.13 project environment with the shared runner requirements and
`requirements-roboskills.txt`. Complete the normal Codex subscription login on
that machine. Credentials stay there; no provider API key is requested.

```sh
PYTHONPATH=src python roboskills_playground.py --port 8797 \
  --recording-root /absolute/path/to/persistent-recordings
```

The site bridge is in `integrations/roboskills/site/worker-agent/physical_worker.py`.
It authenticates only to the public application's worker API, with the configured
worker key supplied via hidden stdin. It uses no privileged hosting bypass.
Keep it and the harness running for website jobs. Physical recordings are camera
footage, not a simulation. Session capabilities and email never enter public run
projections. The current Site restricts shared compute/control submission to its
connected operator; demonstrations, live views and run metadata are public.

## Verification and limits

The first physical website run453a9a037e874840ad4382597c25e8c1 reached
AWS trajectory submission for ep_4518061f91c24d0d, then exposed an adapter status
bug. It was not retried. The status boundary is fixed, and the provider now
composes shared geometry/camera components instead of inheriting another policy's
function-call lifecycle.17 tests and8 subtests pass with the optional runtime.
The station was reconciled parked with torque off. After the owner reaffirmed
the standing authorization, the same website test was allowed and executed
RoboSkills on real arms. Run `249450342a5e4286b9d406d3e8738d34` retained a public
physical replay and receipt. The paired lift measured 14.04 / 14.38 mm against
20 mm requested, so the agent ended at its 3 mm tolerance check without further
motion. The completed-run replay and selecting it from history were verified;
anonymous byte-range access returned206. The arms parked with torque off.
This verifies the real integration, not task success or the15-second target:
packet preparation alone took41.6 seconds after Run. Automatic review still
blocked publication of the older failed-test clip. Full timing, wait-stage and
cross-surface identity qualification remain open.

The native simulation verification `native-lift-20261030` generated an actual
MuJoCo scene and demo. The demo solved8/8 seeds; the build was rejected because
robot-rest and scene-framing checks failed. The fresh frozen-task solver did not
run. The public site retains its native receipt, code and simulated replay.

See [the completion checklist](COMPLETION-CHECKLIST.md). Unchecked requirements
remain blockers; no complete research-integration claim is made.


## Latest physical verification

Run `2ea288ea830e471a86eb6d1d98971c50` completed the paired20mm lift,
one-second hold and return through the website. Measured rises were17.80mm
left and20.97mm right, within the unchanged3mm Cartesian tolerance. Lift
position errors were2.21/0.98mm; return errors2.14/0.08mm. Gripper changes
were below0.0001. Normal Stop/parking completed; native status verified torque off.

The adapter now accumulates a bounded measured tracking offset only after
matched, settled packet completion (max2 corrections,8mm per Cartesian axis
relative to the original goal). It never retries rejected, failed, timed-out or
uncertain packets. Existing IK/workspace/pacing/gateway checks stay intact;
no motor gains or hardware safety limits changed. A latched failure cannot be
cleared by the model calling finish. Sol is separately identified as the planner.

[Physical replay](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/2ea288ea830e471a86eb6d1d98971c50/assets/physical.mp4)
and [measured verification](verification/2026-10-30-lift-return.json). The new
replay was played and seeked in the website; anonymous byte-range access206.
Persistent progress retains actual completed stages and failed accuracy checks.

The owner has excluded queue-admission waiting from this integration's timing
budget. Reassessment of the existing recording gives a conservative adjusted
Run-to-visible-motion upper bound14.442s, retaining1.828s submission time and
excluding only the measured95.331s queued interval. This run passes the amended
per-Run criterion. Original raw times remain retained; entry-to-motion and
other development runs are not automatically reclassified. See the checklist's
owner exception and timing receipt. No queue/readiness check was bypassed.

Current hosted source: `ca4ab9c843c49135e8845c87cbb00bf5cf6e42d8` (Sites version11). Worker continuity recovery uses detached processes, isolated physical/simulation credentials, and preserved no-retry semantics. Both hosted readiness checks were online after the launcher exited. Physical motion evidence is unchanged; see the checklist for remaining qualification.
