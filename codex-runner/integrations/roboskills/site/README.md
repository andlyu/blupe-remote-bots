# RoboSkills × BluPe

Timing contract update (October 30, 2026): the shared harness now requires
15 seconds after settled startup Home (or documented no-Home robot readiness)
and 30 seconds after Run/Start excluding evidenced initial queue-admission wait.
Site entry is context only. References below to older timing gates are preserved
historical assessments. The 107.56-second packet-preparation time and approximate
97-second queue/readiness description do not establish a queue-adjusted pass
without matched admission, Home/readiness and visual motion evidence. Current
timing remains unverified; see the maintained checklist. No retest was performed.

A website showing how RoboSkills' Agentic Simulation workflow works with two YAM arms. The two official examples are **Lift a tray** and **Thread a rope**. Demonstrations are embedded directly from OpenRoboKit, with attribution and upstream-reported seed results. New jobs use the actual pinned build → freeze → solve → native-check workflow, not an animation substitute.

## Website

Install through the Sites installer, then `npm run dev`. The hosting manifest declares D1 (`DB`) and R2 (`BUCKET`). Generate schema changes with `npm run db:generate`; Sites applies hosted migrations during publication. The public website shows both bimanual demonstrations and the local execution workflow without sign-in. Physical runs need no operator sign-in: visitors confirm their name/email and enter the normal BluPe queue. A private browser cookie retains Stop ownership. Shared simulation execution remains restricted to its configured operator. Production sets PHYSICAL_WORKER_TOKEN, SIMULATION_WORKER_TOKEN and RUNNER_OWNER_EMAIL as secrets. Each role uses its own token; WORKER_TOKEN remains a fallback only when that role has no dedicated token.

## Simulation worker

Keep the exact upstream checkout outside this repository:

```sh
git clone https://github.com/openrobokit/roboskills.git ../roboskills
git -C ../roboskills checkout 8a2860234768b4bec981994d1c14fa380a2c8c7f
bash ../roboskills/src/roboskills/workflows/agentic_sim/setup.sh
```

Run `worker-agent/worker.py` in that interpreter, passing one JSON configuration object on stdin. Keys: `origin` (this Site), `workerToken` (the matching runtime secret), `python` (absolute simulator interpreter), `runs` (absolute output directory), `model` (default `gpt-6-astra`), `hours` (per-stage limit, default 1). Obtain credentials through supported Site management; do not commit them. The process must remain running for new jobs. Heartbeat expiry disables new submission immediately and records abandoned active work explicitly; no uncertain run is automatically repeated.

For GPT models the wrapper binds upstream's existing tool-free `core.llm.codex` conversation transport to the launcher. The wrapper also states the worker’s actual simulator availability in the build context. The build logic, solver, task fingerprinting and native checks are unchanged. Codex uses the operator's existing ChatGPT login; Claude models use the upstream default. No global skills are installed.

The development runtime explored here has MuJoCo and Blender. Upstream's full Linux setup also includes PyBullet and Newton; a runtime must advertise only what is actually installed. See VERIFICATION.md for measured qualification and remaining limits.

## Physical YAMs

The physical panel runs the RoboSkills Python agent through the shared BluPe remote-arms provider and RunnerController. Live YAM cameras, real run progress, Stop, measured results and retained physical replays are integrated into this website. The existing BluPe queue, leases and validated command gateway govern hardware execution. Simulation outputs are reviewed separately; simulated joint trajectories are not transferred onto hardware.

## Checks

`npx tsc --noEmit`, `npm run build`, upstream `tests/workflows/agentic_sim`, local API tests, and browser verification. Source provenance lives in the Sites Git repository; simulation receipts record the upstream revision and model.

## BluPe remote-arms connection

The physical panel is connected to the shared remote-arms harness, not a navigation handoff. `worker-agent/physical_worker.py` uses `remote_yam.runner_policy_client.RunnerPolicyClient` against the configured `roboskills_playground.py` provider. The provider uses the pinned RoboSkills persistent Python agent loop with live RGB and the existing calibrated BluPe Cartesian/IK packet component. RunnerController retains the queue, lease, command validation, measured completion, Stop and parking lifecycle. Physical inference defaults to gpt-6-sol (configurable with --inference-model); the harness Model is RoboSkills. Simulation inference remains separately configured. This physical adapter does not replay simulated joint targets or advertise the full RoboKit/SAM tool API.

Start the shared provider with the documented port8797 and a persistent recording directory. Start the physical bridge with one hidden-stdin JSON configuration: origin, workerToken, python, runs and harness (loopback origin). This public Site requires only application worker authentication; no hosting bypass token is needed. Keep the local model login and session capabilities on the runner. Run/status/Stop use the same retained visitor capability.

Live station cameras, public run metadata and simulation results open without sign-in. Email and capabilities stay outside public run projections. Physical queue participants submit jobs with editable actual name/email, without operator sign-in. The owner explicitly requested removing that gate. The earlier anonymous simulation-compute restriction remains unchanged.

The real native simulation verification is retained under public/verification/native-lift-20261030: build rejected, demo8/8, solver not run. It is an observed workflow failure, not a successful completed build-and-solve. The first physical test exposed a status-lifecycle bug; it was stopped and reconciled parked/off. Later verification run `2ea288ea830e471a86eb6d1d98971c50` completed the20mm goal,1s hold and return within3mm tolerance. Measured rises17.80/20.97mm and return errors2.14/0.08mm; grippers unchanged. Actual footage plays in the public physical history. Bounded tracking corrections require matched settled feedback; failed or uncertain packets are never retried. The owner clarified that evidenced queue-admission waiting is excluded. The successful run has a conservative adjusted Run-to-visible-motion upper bound of14.442s. The current shared contract additionally requires matched post-Home timing, which remains unverified for this historical run. An older failed clip's publication remains explicitly blocked by tool review. See [the preserved checklist](docs/COMPLETION-CHECKLIST.md).

The shared harness is installed locally: startup instructions in AGENTS.md, exact contract in docs/BLUPE-HARNESS-CONTRACT.md, and the standard-library scope renderer in tools/blupe_harness.py. These grant no permission by themselves and do not change authentication or reviewer policy.

## Keeping the connection running

`python worker-agent/launch.py` reads one hidden-stdin JSON object and starts detached services. Configure `origin`, the absolute virtualenv `python` path, `runsRoot` (persistent local outputs), `sharedRunner` (the BluPe remote-arms checkout), and `physicalToken` / `simulationToken` matching the corresponding hosted secrets. Either role can be omitted. Optional `providerPort` defaults to8797; `simulationModel` defaults to gpt-6-astra; `hours` defaults to1. Do not put credentials in arguments, source or saved JSON.

The launcher exits after starting services, so they do not depend on the chat terminal remaining open. It stores only process IDs and log paths in `runsRoot/services.json`; tokens pass to workers through stdin. It refuses duplicate live service IDs or an occupied provider port, never kills an existing service, and never automatically restarts or replays a task. Heartbeat readiness on the website is the final availability check. Keep the shared runner and pinned RoboSkills source in persistent directories; deleting a temporary source checkout breaks imports on recovery. This runs on the configured local machine while it is awake; it is not a hosted always-on compute service or reboot supervisor. Inspect logs and reconcile any interrupted run before an explicit recovery launch.

Launcher regression check: `python -m unittest discover -s worker-agent -p test_launch.py -v`.

## Connection recovery and operator access

Transient station/history errors clear after a successful refresh; action failures remain visible until a new action. A Refresh connection control preserves the current task and selected replay. Public visitors can submit the physical form directly after confirming their name and email. Viewing cameras, simulation evidence and replays requires no account; physical execution uses BluPe queue/lease safeguards and browser-scoped Stop ownership.

The physical bridge distinguishes observed queue entry, confirmed admission, arm preparation, model decisions and measured packet execution. Completed progress retains observed timestamps. These are status receipts, not a substitute for visually verified physical onset or matched startup Home timing. New lifecycle projections omit contact details and capabilities.
