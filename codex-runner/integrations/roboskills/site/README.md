# RoboSkills × BluPe

A website showing how RoboSkills' Agentic Simulation workflow works with two YAM arms. The two official examples are **Lift a tray** and **Thread a rope**. Demonstrations are embedded directly from OpenRoboKit, with attribution and upstream-reported seed results. New jobs use the actual pinned build → freeze → solve → native-check workflow, not an animation substitute.

## Website

Install through the Sites installer, then `npm run dev`. The hosting manifest declares D1 (`DB`) and R2 (`BUCKET`). Generate schema changes with `npm run db:generate`; Sites applies hosted migrations during publication. The public website shows both bimanual demonstrations and the local execution workflow without sign-in. Shared-worker execution remains restricted to the authenticated operator identified by RUNNER_OWNER_EMAIL; no anonymous worker admission is enabled. Production must set WORKER_TOKEN and RUNNER_OWNER_EMAIL as secrets.

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

The site links to the existing BluPe playground and copies the task instruction for preparation. It does **not** deploy generated simulation code onto physical hardware or claim successful sim-to-real transfer. The existing physical queue, leases, controls and live views remain owned by BluPe. Physical method execution and its footage require a separately verified adapter.

## Checks

`npx tsc --noEmit`, `npm run build`, upstream `tests/workflows/agentic_sim`, local API tests, and browser verification. Source provenance lives in the Sites Git repository; simulation receipts record the upstream revision and model.

## BluPe remote-arms connection

The physical panel is connected to the shared remote-arms harness, not a navigation handoff. `worker-agent/physical_worker.py` uses `remote_yam.runner_policy_client.RunnerPolicyClient` against the configured `roboskills_playground.py` provider. The provider uses the pinned RoboSkills persistent Python agent loop with live RGB and the existing calibrated BluPe Cartesian/IK packet component. RunnerController retains the queue, lease, command validation, measured completion, Stop and parking lifecycle. Physical inference defaults to gpt-6-sol (configurable with --inference-model); the harness Model is RoboSkills. Simulation inference remains separately configured. This physical adapter does not replay simulated joint targets or advertise the full RoboKit/SAM tool API.

Start the shared provider with the documented port8797 and a persistent recording directory. Start the physical bridge with one hidden-stdin JSON configuration: origin, workerToken, python, runs and harness (loopback origin). This public Site requires only application worker authentication; no hosting bypass token is needed. Keep the local model login and session capabilities on the runner. Run/status/Stop use the same retained visitor capability.

Live station cameras, public run metadata and simulation results open without sign-in. Email and capabilities stay outside public run projections. The connected operator submits jobs with editable actual name/email. Opening anonymous shared compute was rejected by automatic approval review and has not been enabled.

The real native simulation verification is retained under public/verification/native-lift-20261030: build rejected, demo8/8, solver not run. It is an observed workflow failure, not a successful completed build-and-solve. The first physical test exposed a status-lifecycle bug; it was stopped and reconciled parked/off. Later verification run `2ea288ea830e471a86eb6d1d98971c50` completed the20mm goal,1s hold and return within3mm tolerance. Measured rises17.80/20.97mm and return errors2.14/0.08mm; grippers unchanged. Actual footage plays in the public physical history. Bounded tracking corrections require matched settled feedback; failed or uncertain packets are never retried. The15s target remains unmet, including about97s queue/readiness in the latest test. An older failed clip's publication remains explicitly blocked by tool review. See [the preserved checklist](docs/COMPLETION-CHECKLIST.md).

The shared harness is installed locally: startup instructions in AGENTS.md, exact contract in docs/BLUPE-HARNESS-CONTRACT.md, and the standard-library scope renderer in tools/blupe_harness.py. These grant no permission by themselves and do not change authentication or reviewer policy.
