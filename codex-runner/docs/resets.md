# Environment resets: replay and measured cube positioning

## Reset the environment through the hosted API

To reset YAM's bin and blocks, run the example API client from a current checkout
of this repository. From the repository root, using Python 3.10 or newer:

```bash
cd codex-runner
python3 examples/reset_environment.py \
  --origin https://playground.blupe.io \
  --robot-id yam-1 \
  --runner-name "Your name" \
  --email "you@example.com" \
  --start --wait \
  --session-file /tmp/yam1-reset-session.json
```

Replace the name and email with your own. The command submits one **Reset bin**
job through the Playground API, joins the normal robot queue, and waits for its
result. The hosted backend coordinates recorded box replay, camera-clear Home,
then cube reset. The selected reset defaults to a ten-minute run deadline.

`--start` requests physical execution. Ctrl-C while waiting requests Stop. Keep
the same private session file to inspect or stop that run from another terminal:

```bash
python3 examples/reset_environment.py --status --session-file /tmp/yam1-reset-session.json
python3 examples/reset_environment.py --stop --session-file /tmp/yam1-reset-session.json
```

If the start response is unclear, check status before submitting another start.
Continue checking status after requesting Stop to confirm the run has ended.
The session file contains authentication material and is written mode0600; keep
it out of source control and logs. To discover the configured reset without
starting a job, run:

```bash
python3 examples/reset_environment.py --origin https://playground.blupe.io --robot-id yam-1
```

The hosted YAM reset is deployed. Deployment checks verified the hosted policy,
camera reads and API discovery/status; those checks do not establish that a
complete physical reset has succeeded.

## Implementation and qualification

The reusable implementation lives in [`remote_yam.resets`](../src/remote_yam/resets/),
including the recorded replay engine/editor, RGB-D cube fitting, grasp and
placement planning, geometry audits, controller I/O, and combined Python runner.
It does not import a private `blupe_evals` package or shell to a private runner.
Station recordings, target records, calibration, collision assets, controller
addresses and credentials are external configuration.

Cube-only configured policies may select `execution: "session_cube"` with an
absolute `session_config` and explicit `execution_policy`. `CubeSessionPolicy`
joins the normal queue and receives its measured Home handoff. It runs the same
cube program through lease-bound `yam_cube_reset` execution requests, without
manual initialization, local-pose reservation or pausing Auto Queue. Existing
queue/session Stop and completion cleanup retain ownership. The Session API and
native controller must support this executor; a geometry-off cube profile is
an explicit native operator selection, separate from ordinary model packets.
Source/resource hashes are checked before queue admission. Never automatically
retry an uncertain motion. The replay qualification below is a separate flow.

An earlier integration trial completed box replay and
its no-motion handoff, then failed planning from the measured endpoint before
any cube motion. Subsequent software and deployment checks cover the
one-Home/fresh-image/staging sequence, configuration and transport. They do not
qualify the complete reset as physically successful. Check installed session
metadata before requesting a real reset.

## Select it like another policy

A station administrator configures `reset_bin`, with label **Reset bin** and
model identity `reset-bin-v1`. It appears in the same composer/settings selector
as the configured Astra and Claude models. Select it, then use the usual Run and
Stop controls. No model call chooses the transition between replay and reset.
Selecting a model again restores the previous task prompt.

Discover configured choices without moving:

```sh
cd codex-runner
python examples/reset_environment.py --origin http://127.0.0.1:8787
```

Run once, retain the visitor capability privately, and monitor:

```sh
python examples/reset_environment.py --start --wait --session-file /tmp/reset-session.json
# From another terminal, using the SAME visitor capability file:
python examples/reset_environment.py --status --session-file /tmp/reset-session.json
python examples/reset_environment.py --stop --session-file /tmp/reset-session.json
```

The file is written mode0600 and contains authentication material; keep it out
of source control and logs. `--start` requests physical execution. Ctrl-C during
`--wait` requests Stop. Stop acceptance is not confirmation that Hold completed;
continue polling. A timed-out or ambiguous start is never retried automatically.

The reusable client is also importable:

```python
from remote_yam.runner_policy_client import RunnerPolicyClient

client = RunnerPolicyClient("http://127.0.0.1:8787", robot_id="yam-1")
session = client.connect()
assert "reset_bin" in session.get("configured_providers", {})
run = client.start("reset_bin")
state = client.status()  # Checks the returned attempt_id against this run.
# client.stop()         # Request cancellation; keep polling status.
```

These are runner `/api/*` routes. The public `/v1/sessions` API remains the
low-level model/trajectory SDK; it has no deployed `/v1/reset` operation.
A client choosing a configured reset does not create a second gateway session,
automatic Home, motor driver or controller service.

## Call the actual combined implementation

Install the optional perception/planning dependencies and select the public source:

```sh
cd codex-runner
python -m pip install -r requirements-resets.txt
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
python -m remote_yam.resets --config /path/to/private-station.json \
  --output /path/to/new-evidence-directory --request-id operator-chosen-run
```

Or call Python directly, including an existing controller connection factory:

```python
from remote_yam.resets import run_reset

result = run_reset(station_config, new_output_directory, request_id="one-run")
assert result["goals_reached"]  # A completed process alone does not prove this.
```

`run_reset` takes a JSON-file path or dictionary. It creates one nonblocking
per-robot process lock and one shared controller connection. It requests the
selected recorded replay once, checks that exact request completed in Hold,
then calls the cube positioning implementation **in-process** with the same
connection. The selected combined station profile performs exactly one existing
guarded native Home, captures a fresh overhead observation, then positions cubes.
The recorded replay's generated Home tail stays off, and native startup does not
repeat the acknowledged Home. No Zero, Park, torque-off or controller restart is
added. Genuine view/pickup clearance remains part of the selected planner. Existing native limits, motor health,
tracking, gripper bounds and Stop still apply.

The Mac orchestrator cannot directly access the Python operator object in an
already running Jetson process. Its shared worker crosses the existing loopback
Replay/local-pose API boundary to that primary motor owner. Importing the public
code does not open a motor connection. Native integrators can also use the public
[`RecordedReplay`](../src/remote_yam/resets/recorded_replay.py) engine with their
**existing** controller bridge and guard; they must supply the episode directory.

`io_factory` and `cube_program` are injectable Python arguments for integrations
and tests. Public-only tests run the actual combined sequencer with inert I/O,
and exercise the actual replay retiming, RGB-D surface fit and gripper math.
They do not substitute a private runner.

## Replay and pick/place components

- [`replay_edit.py`](../src/remote_yam/resets/replay_edit.py) validates immutable
  source arrays and recipes, crops/retimes recorded actions and optionally
  generates a Home tail. The combined recipe explicitly omits that generated tail;
  it does not rewrite recorded box handling or the saved global edit.
- [`ReplayTransport`](../src/remote_yam/resets/replay_transport.py) calls the
  existing controller's replay start/status/Hold exactly once per request.
  Modern interfaces use advertised operations and process/version preconditions.
  An older installation requires an explicitly configured, source-hashed contract;
  there is no automatic legacy/maintenance fallback or credential default.
- [`PickupFeedbackCubeProgram`](../src/remote_yam/resets/yam_cube_size_profile.py)
  uses measured RGB-D cubes, IK and geometry audits to pick/place to configured
  goals. [`cube_cli.main(argv, shared_io=io)`](../src/remote_yam/resets/cube_cli.py)
  is its callable entry point for the selected cube-only routine. Pass the station's
  explicit `cube_args`, output and transport arguments inside a
  [`station.configured(resources)`](../src/remote_yam/resets/station.py) context.
  Fixed colors are blue/orange/yellow; goals are immutable input records, not public
  hardcoded coordinates. The full known-size RGB-D fitter is included.

## Station configuration

`private-station.json` uses schema `remote-yam-reset-station-v1`:

| Field | Required deployment input |
| --- | --- |
| `transport` | Explicit trusted SSH destination; optional identity-file path |
| `io_routes` | Operation→`[port,path]` map for the existing native status/pose/camera APIs |
| `replay` | Controller origin; optional qualified `legacy_contract` with source hashes and expected status fields |
| `recipe` | Immutable selected `abc-replay-edit-v1` episode/source/calibration identity and crop/timing; `return_home:false` |
| `cube_args` | Explicit public cube CLI arguments: calibration, goals, collision parts, workspace, planning profile and asset root; selected combined profile includes `--home-after-replay` and `--staging-feedback` |
| `resources` | Goal file/content hash, gripper asset directory, collision-model loader source, station base/joint geometry, optional existing startup command |

`resources.auditor` defaults to the public installed-geometry auditor. External
collision preparation code/assets must be installed and bound by deployment;
this package does not bundle a station's measured meshes/calibration. Runtime
resource checks retain the selected hashes and native calibration/goal binding.
Do not change a configured/frozen implementation during an active run.

To register the public implementation in the existing local runner, set
`YAM_LOCAL_POLICY_CONFIG` before starting it. Configuration schema:

```json
{
  "schema": "blupe-managed-policies-v1",
  "policies": {
    "reset_bin": {
      "robot_id": "yam-1",
      "label": "Reset bin",
      "model": "reset-bin-v1",
      "task": "Reset bin",
      "help": "Replay box emptying, then reset measured cubes to saved goals.",
      "command": ["/path/to/python", "-m", "remote_yam.resets", "--config", "/path/to/private-station.json", "--output", "{output}", "--request-id", "{request_id}"],
      "recording_root": "/path/to/durable-reset-receipts",
      "sha256": {"/path/to/frozen-source.py": "EXPECTED_SHA256"}
    }
  }
}
```

The configured Python must import this public package, for example through the
`PYTHONPATH` set above. Commands/endpoints are administrator configuration and
cannot be supplied by a Run HTTP payload. The station operator activates a reviewed
runtime only after its required qualification. Registration/selection is not proof
that a physical reset succeeds.

## Existing authenticated Run/status/Stop API

Use one visitor cookie and CSRF token from `POST /api/session`; send the same
cookie thereafter, matching `Origin`, `Content-Type:application/json` for POST,
`X-Yam-Runner-Token` on mutations, and `X-Blupe-Robot:yam-1` on every request.
No model-provider key is needed for this configured policy. Authentication values
are runtime data, never public configuration.

```sh
BASE=http://127.0.0.1:8787
COOKIE=$(mktemp)
SESSION=$(curl -fsS -c "$COOKIE" -H "Origin: $BASE" -H 'X-Blupe-Robot: yam-1' \
  -H 'Content-Type: application/json' -d '{}' "$BASE/api/session")
printf '%s' "$SESSION" | jq -e '.configured_providers.reset_bin'
TOKEN=$(printf '%s' "$SESSION" | jq -er .csrf)
curl -fsS -b "$COOKIE" -H "Origin: $BASE" -H 'X-Blupe-Robot: yam-1' \
  -H "X-Yam-Runner-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"provider":"reset_bin","model":"reset-bin-v1","prompt":"Reset bin","runner_name":"API operator","run_duration_s":600}' "$BASE/api/run"
curl -fsS -b "$COOKIE" -H 'X-Blupe-Robot: yam-1' "$BASE/api/status"
# Stop if needed, then keep polling the status request above:
curl -fsS -b "$COOKIE" -H "Origin: $BASE" -H 'X-Blupe-Robot: yam-1' \
  -H "X-Yam-Runner-Token: $TOKEN" -H 'Content-Type: application/json' -d '{}' "$BASE/api/stop"
```

Start returns the existing `attempt_id`; executable status/results also carry
`request_id`. Start is **not idempotent**. On an ambiguous response, inspect status
with the same visitor rather than retrying. Handles do not authorize another
visitor to retrieve or stop a run. Busy/overlapping local runs return409. A worker
remains busy until cancellation has a terminal receipt/process exit.

Top-level states are `preparing`, `running`, then `stopped` or `failed`.
Read `provider.managed_execution`: `phase`, atomic stage `progress`, and terminal
`result`. Completion requires `phase:complete` and `result.goals_reached:true`.
Failure, Stop, replaced ownership or uncertain replay cannot start the cube stage.
Inspect retained comparison/timing/error receipts; no movement is automatically
retried. Failed planning time is included in telemetry even when no plan exists.

## Fresh cube-only resets and hosted runners

`python -m remote_yam.resets.cube_runner --config station.json --output RUN_DIR --request-id RUN_ID`
runs the configured public cube CLI without Replay or an extra replay Home. Each
output directory must be fresh. Station resources and20mm closing remain explicit
configuration; native motor/force/current protections and cube Stop are retained.
It writes request-bound progress and terminal receipts for `ManagedCommandPolicy`.

For a hosted runner, `ConfiguredPoliciesMixin` loads operator-owned
`YAM_CONFIGURED_RUNNERS_FILE` metadata and a `RemoteRunnerPolicy` proxy. That proxy
uses the existing local runner visitor/CSRF/Run/status/Stop API over an operator
SSH tunnel; browser payloads cannot supply commands, endpoints or station paths.
`runner_origin` is the local runner's configured origin; optional `transport_origin`
is a trusted loopback tunnel endpoint. The latter sends the original Host/Origin.
No robot keys/calibration/recordings are uploaded to the hosted web server.
The host application retains its own allowance/admission policy. A start write is
attempted once, ambiguous responses are reconciled with the same visitor, and
Stop retains ownership until the underlying executable terminates.

The size-aware and pickup-feedback CLI accepts `--feedback-extra-open-gap-mm`
(default20). For a30mm cube and the existing10mm pregrasp clearance, setting40
requests80mm pregrasp opening. Close/carry (`--feedback-close-gap-mm`, default20)
and release40mm remain independent. Warm-started reference plans receive the
selected opening too; this option does not change native gripper travel/guards.
## Execute the reset in the hosted backend

A hosted runner can own `CubeSessionPolicy` directly, using the same normal robot
queue and Session API execution as the local session policy. In the existing
operator-owned `YAM_CONFIGURED_RUNNERS_FILE`, select `execution: "session_cube"`:

```json
{
  "reset_bin": {
    "robot_id": "yam-1",
    "label": "Reset bin",
    "model": "reset-bin-replay-session-v5",
    "task": "Reset bin",
    "help": "Recorded box Replay, camera-clear Home, then cube reset.",
    "execution": "session_cube",
    "execution_policy": "controller-faults",
    "session_config": "/var/lib/yam-reset/station.json",
    "recording_root": "/var/lib/yam-reset/runs",
    "default_run_duration_s": 600,
    "sequence": ["recorded_box_replay", "camera_clear_home", "cube_reset"],
    "sha256": {"/var/lib/yam-reset/station.json": "DEPLOYMENT_SHA256"}
  }
}
```

Use the installed station's model identity and complete source/resource hash
manifest. The hosted factory constructs the actual session policy in the hosted
process; it does not open a second runner session or instantiate a
`RemoteRunnerPolicy`. The browser and API both use the same `/api/run` route,
queue, native execution, progress receipts and Stop lifecycle. Existing remote
runner configurations remain supported when `execution` is omitted or is
`"remote_runner"`.

Before activation, install the station configuration, calibration, immutable
goals, gripper meshes, collision components and public reset dependencies on the
host. Rebind their paths and regenerate the administrative hash manifest. The
station camera/state transport must be reachable from the host directly to the
robot; pointing it at a visitor's machine retains that dependency. The current
session policy uses an explicitly configured SSH camera/state transport, while
motor requests use its existing Session API lease. Do not copy a user's login
credentials or assume a private LAN address is reachable from the hosted server.
Installing this factory alone does not migrate assets, activate a station, or
establish that a physical reset succeeds.

The public CLI also accepts hosted admission fields. From `codex-runner`:

```sh
# Discovery only; does not start a reset.
python examples/reset_environment.py --origin https://playground.blupe.io

# Starts one physical reset using the configured hosted policy.
python examples/reset_environment.py --origin https://playground.blupe.io \
  --robot-id yam-1 --runner-name "Remote operator" --email "you@example.com" \
  --start --wait --session-file /tmp/yam-reset-session.json

# Later, retain this exact visitor file for status or Stop.
python examples/reset_environment.py --status --session-file /tmp/yam-reset-session.json
python examples/reset_environment.py --stop --session-file /tmp/yam-reset-session.json
```

The Python equivalent is `client.start("reset_bin", email="you@example.com",
runner_name="Remote operator")`. The host application still enforces its normal
email, allowance and visitor authorization rules. These fields do not grant a new
permission or change the execution transport. After an ambiguous response,
inspect the same visitor's status instead of sending another start.

# Recorded box Replay in a queue session

Set `default_run_duration_s: 600` in both the local policy and hosted proxy
configuration to default Reset bin to ten minutes. The model selector applies
that policy's default; other providers keep five minutes. Explicit changes are
remembered per provider/robot for the current page, including a browser-restored
nondefault value. Re-selecting a provider does not overwrite its explicit choice.
Requests that omit a duration also receive the configured server default.
The hosted proxy forwards the owning controller's selected duration to its child
runner, so both deadlines match. Explicit deadlines and normal Stop remain.

For the combined Reset bin, configure `sequence` as
`["recorded_box_replay", "camera_clear_home", "cube_reset"]` and bind the existing
station `recipe` (saved source/edit/calibration, generated Home disabled). The
session adapter executes the installed primary Replay engine through the same
native lease executor, waits for its matching complete/Hold receipt, performs
exactly the existing single camera-clear Home, then starts fresh tabletop sensing.
There is no manual Replay reservation, queue pause, intermediate Park, torque
cycle, reinitialization or second Home. Legacy cube-only configurations retain
their existing behavior.

All three stages keep the same session/episode/lease. Normal Stop cancels Replay
or cube motion and prevents the next stage. Failed, cancelled or uncertain Replay
never advances or resends execution. Sequence receipts and stage status are saved
under the run's `sequence/` directory. No physical trial is implied by installing
this configuration; the operator launches it from the website.
