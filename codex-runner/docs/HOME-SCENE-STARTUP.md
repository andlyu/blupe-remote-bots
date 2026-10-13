# Cached home-scene startup

The shared runner implements an optional version-1 extension with the BluPe
Session API and YAM station controller. All three changes must be installed to
use the overlap. No deployment or physical-robot validation is implied by the
simulated tests.

## Lifecycle

On `policy_complete`, the station's existing AutoQueue owner returns the arms
Home, confirms settled joints and open grippers, captures all three camera views
between two measured pose reads, and saves `state/home-scene.json`. It then uses
the existing validated Park at Zero and torque-disable path, even if another
visitor is queued. Capture failure still allows normal parking. Stop, runtime
expiry, emergency stop, and faults keep their existing cleanup behavior; they
do not request an extra trip Home for capture.

When the parked station begins its next automatic startup, it offers that scene
only to the current robot queue head. The Session API checks the robot identity,
queue head, and absence of another active lease. This is permission to plan,
not permission to move. Astra can plan while the existing station owner launches
and calibrates grippers and homes. A queued visitor behind another task receives
no usable offer. The cache is consumed once; the next normal completion creates
a new scene.

The runner supports the standard RGB YAM `AstraAdapter`, `OpenAIAdapter`, and
`CodexAdapter` trajectory paths. Depth policies, other robot embodiments,
ASPIRE session policies, and legacy single-action transport are not included.
Both Responses vision input and Codex's image attachments use the saved bytes;
model text explicitly calls these the *future home starting state*, not live
feedback. First-call wandering is suppressed when the extension is active.

## Acceptance and fallback

Before first task motion, a cached trajectory must have:

- A valid locally generated trajectory and the same run identity.
- Fresh Session API state with the actual matching lease, episode, first
  observation cursor, and no active trajectory.
- Fresh measured hardware feedback confirming Home, settling, safe state, and
  open grippers. Joint readings must agree with the planning pose within 0.25°.
- A station receipt binding the scene to this startup, process boot, and robot
  configuration hash.
- A new coherent three-camera set captured after arrival Home, no more than two
  seconds old, with source capture timestamps and exact JPEG hashes matching
  the saved scene. The final hardware/lease check runs again before dispatch.

**The image comparison is deliberately strict. Camera noise, exposure changes,
re-encoding, or missing source timestamps can cause frequent fallback on real
cameras.** It makes no claim that changed objects are harmless. There is no
measured field cache-hit rate or live latency improvement yet. Occluded changes
cannot be detected from RGB images; existing station motion checks still apply.

Changed, missing, older-than-120-second, wrong-robot, wrong-configuration, or
unverifiable scenes trigger fresh observation and inference. A failed speculative
request or model `done` result also falls back. Discard clears the speculative
model history, pending tool, orientation reference, and Codex resume state.
Runtime steering invalidates an already prepared cached plan. The accepted first
packet goes through the ordinary idempotent dispatch path exactly once.

Stop revokes station execution first and cancels and joins the run-owned planning
worker. Codex terminates its child process using its existing cancellation path.
Responses body reads are interrupted when possible; connection/header setup
remains bounded by the existing HTTP timeout. Teardown can therefore wait for
that transport timeout, but the worker is drained before reuse. No speculative
output is imported into another run.

## Timing

The runner records elapsed monotonic time through the **first executable
trajectory**, including any invalid-response corrections and local planning.
It does not learn from total run length or final text completion. The API keeps
the last 20 accepted, deduplicated samples per robot configuration and provider
profile (model, endpoint, effective system prompt, workspace, reasoning effort,
and response speed). Samples are process-local; API restart returns to a cold
start. Reports come from the authenticated runner and are not independent
server-side measurements of model execution.

The station measures calibration/startup elapsed time and settling overhead.
Target home duration is approximately:

```
mean first executable plan - elapsed startup/calibration - mean settling overhead
```

Before measured settling samples exist, the allowance is explicitly a
provisional one second. Without inference samples, Home keeps its normal safe
trajectory. A requested duration is clamped to 0–30 seconds and passed as
Ruckig's minimum duration. Existing velocity, acceleration, jerk, collision,
joint, gripper, and settling constraints remain in force; a safety-limited path
can take longer. A fast plan waits for Home; a fast robot waits at Home.

Runner `home_scene` journal events report planning, hit/fallback reason,
first-plan duration, robot wait, plan wait, and sample publication. Station logs
record startup/calibration, commanded and actual Home duration, settling basis,
sample count, and target duration. The persisted scene includes camera mapping,
frame sequence/hash/timestamp, measured joints/grippers, configuration digest,
process identity, and capture bracket duration. A saved file is evidence only
and is not reloaded as valid authority after a station restart.

## Wire extension and compatibility

Stations request `home_scene_version: 1` in registration; supporting APIs echo
it only to those stations. Old stations get their unchanged registration reply.
The local camera relay emits original source epoch timestamps on both JPEG
snapshots and MJPEG parts; the API camera publisher/proxy preserves them.
Old APIs do not receive new station messages. Runners encountering an absent
endpoint use the existing fresh-observation path.

Authenticated runner endpoint: `GET/POST /v1/sessions/{id}/home-scene`.
POST registers a profile hash and optionally reports one measured executable-plan
sample with the robot configuration hash. GET returns the queue-head offer and,
after station preparation, the actual lease-bound readiness receipt.
Authenticated station message: `type: home_scene`, with `phase: offer`, `ready`,
or `invalidate`. Offers contain the saved scene; ready receipts contain scene,
configuration, boot, session, episode, and lease identities. Ordinary observation
and trajectory schemas are unchanged. These endpoints grant no new motion
capability and cached frames never enter the live robot observation endpoint.

## Validation

Run the ordinary Python and JavaScript suites, then the companion station and
Session API tests. To exercise the actual station, HTTP/WebSocket API, and runner
together with in-memory motor drivers and mocked external model transports:

```sh
BLUPE_HOME_SCENE_STATION=/path/to/blupe-playground-robot-controller \
BLUPE_HOME_SCENE_API=/path/to/blupe-evals \
python -m pytest codex-runner/tests/test_home_scene_integration.py -q -s
```

The integration test needs the station dependencies (including a compatible
Ruckig binary), uvicorn, and both companion changes. It covers cold starts,
cache hits, changed-image fallback, post-completion capture/park/disable, and
measured profile learning for Astra API and Codex subscription paths, plus
cancellation during calibration with zero task commands or extra Home/capture. External
model replies and camera pixels are fixtures; all motor IO uses `SimulatedBus`.
