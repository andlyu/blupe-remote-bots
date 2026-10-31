# RoboSkills on BluPe remote arms

The physical provider runs OpenRoboKit's persistent Python agent loop from
`core.agent.run`, pinned to8a2860234768b4bec981994d1c14fa380a2c8c7f.
The model sees actual RGB images, measured state and a small BluPe tool surface:
`bot.status`, `bot.observe`, `bot.move_to`, `bot.wait`, and `finish`.
The Cartesian/IK component and RunnerController retain the station workspace,
queue, lease, packet validation, correlated measured completion and Stop.
This adapter does not expose the complete RoboKit/SAM API or replay simulation
joint targets. Its physical success score is explicitly unscored.

The harness Model is **RoboSkills**; the underlying inference model is separate
configuration (`gpt-6-astra`). Real name/email remain editable before joining.
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
The station was reconciled parked with torque off. Automatic approval review
blocked a new physical verification and public upload of the existing recording.
No workaround was used. Until that test is authorized and passes, physical
execution/replay and15-second targets remain unverified for the corrected code.

The native simulation verification `native-lift-20261030` generated an actual
MuJoCo scene and demo. The demo solved8/8 seeds; the build was rejected because
robot-rest and scene-framing checks failed. The fresh frozen-task solver did not
run. The public site retains its native receipt, code and simulated replay.

See [the completion checklist](COMPLETION-CHECKLIST.md). Unchecked requirements
remain blockers; no complete research-integration claim is made.
