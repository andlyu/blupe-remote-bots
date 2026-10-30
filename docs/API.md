# Robot API

Connect your model to real robot arms. Read camera images and measured joint
state, run your policy on your computer or model service, and send its next
motion through BluPe. The playground uses this same Session API.

Prefer the ready-made playground? [Run it locally](local-playground.md) or
[open the playground](https://playground.blupe.io/).

## Quick start

Start with public, read-only requests. These do not join a queue or move a robot.
No BluPe credential or model API key is required.

```bash
export BLUPE_API="https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com"
curl --fail-with-body "$BLUPE_API/v1/robots"
curl --fail-with-body "$BLUPE_API/v1/robots/yam-1/queue"
curl --fail-with-body "$BLUPE_API/v1/robots/yam-1/observation"
```

The queue reports station connection and availability. An empty queue or a
successful `/health` response does not mean the robot is ready. The observation
contains measured joint state, readiness/safety fields, timestamps, and camera
URLs. Fetch the returned image URLs to see the scene.

Base URL: `https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com`

The [live v1 JSON schemas](https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com/v1/contracts)
define request and response fields. This endpoint returns JSON Schema, rather
than an OpenAPI/Swagger interface. Deployment-specific bounds can change; check
that contract when building a client. Examples below target ordinary v1 sessions.
The public read contract was checked on October 25, 2026.

## Choose a robot

Use `GET /v1/robots` for registered IDs, then read that robot's queue and
observation. Registration does not establish availability. Discovery includes
calibration links when configured; it does not currently include complete joint
layouts, joint limits, or a machine-readable motion capability profile.

The current connected stations are the two YAM rigs below, checked on October 25,
2026. Use one of these IDs for the examples in this guide.

| Robot | Robot ID | Left / right arm joints | Camera roles |
| --- | --- | --- | --- |
| YAM | `yam-1` | 6 / 6 | `left`, `top`, `right` |
| Robo-house YAM | `robot-ba8413962083809c` | 6 / 6 | `left`, `top`, `right` |

Andrew's single SO101 and MakerMods Bimanual SO101 are currently offline and are
not included as available stations. Their IDs can still appear in discovery.
A registered ID or bundled runner profile does not mean that hardware is online.

**Connected does not mean ready for motion.** Both YAM rigs reported
`available: false` and `mode: "DISABLED"` at this check. Before requesting a turn,
read the selected robot's live queue and observation; follow its readiness and
session feedback rather than treating this table as a live status display.

Both current rigs use six joint angles per arm, in **degrees**, with independent
grippers. Their station geometry and calibrated limits differ; use the profile
for the selected robot. Never mirror or pad an arm.

See [robot selection and profiles](../codex-runner/docs/MULTI-ROBOT.md) and the
camera calibration below. Cartesian frames, workspace bounds, calibration, and
hardware execution checks must match the selected robot.

The shared runner also contains SO101 and [MakerArm integration profiles](../codex-runner/docs/MAKERARM.md)
for separately configured hardware. Those profiles describe client support,
not additional currently connected stations. A single-arm integration sends the
absent arm as `[]` and omits its gripper.

## Authentication

Public monitoring and session creation require no BluPe account credential.
Creating a session returns an opaque **session capability** for that session's
HTTP requests and event WebSocket:

```http
Authorization: Bearer <session_capability>
Content-Type: application/json
```

Keep the capability in your backend process. Do not put it in URLs, page source,
source control, or logs. It is returned at creation, not by later status reads.
The Python client stores and attaches it for you.

A **lease ID** identifies the current grant of robot control. It is distinct
from the capability, and accompanies motion requests together with the episode
ID. Queued sessions may not have an episode or lease yet.

Your model-provider API key or subscription login authenticates inference with
your provider. Keep it separate from BluPe requests. Your policy performs
inference and inverse kinematics in your own process or service; ordinary
trajectory requests contain motion data, not provider credentials or weights.

## Session lifecycle

Your program joins the selected queue, waits for control and fresh feedback,
then repeats **observe → infer → submit → wait for execution**. When finished,
it sends Stop to release the session.

### Create a session

`POST /v1/sessions` creates a real queue entry. Example request body:

```json
{
  "schema_version": 1,
  "robot_id": "yam-1",
  "prompt": "Place the green block on the plate",
  "run_duration_s": 300
}
```

Ordinary sessions default to **300 seconds**, with a supported range of
**60–600 seconds**. The live schema also describes conditional extended durations
for `provider: "dream"` or `"dream_flash"`; those are provider-specific sessions,
not a way to extend an ordinary trajectory run. Use the duration and conditions
supported by the selected runner and deployment.

Optional creation fields include `runner_name`, `email`, `email_run_video`, and
`public_conversation`. A video-email request requires an email address; delivery
also depends on the runner/hosted integration. See [video email behavior](../codex-runner/docs/RUN-VIDEO-EMAIL.md).

HTTP 201 returns `session_id`, `session_capability`, `status`, `position`,
`episode_id`, `lease_id`, `lease_expires_at`, `latest_observation_step`, and
`events_url`. Episode/lease fields may be null while queued. Save the creation
response privately. Session creation has no idempotency key: do not automatically
create another session after an ambiguous response.

### Wait for control

Open the returned event path on the same API host, using `wss://` and the Bearer
header in the WebSocket handshake. The Python `open_events()` method demonstrates
this. Browser WebSockets cannot set that header; use a backend client.

A normal lifecycle is `queued → preparing → running → complete → resetting`.
Other terminal outcomes include `stopped`, `timed_out`, `disconnected`, and
`safety_aborted`. Treat `resetting` as terminal for the client. Being queued or
receiving a lease alone does not establish physical readiness. Wait for fresh
measured, homed/settled hardware feedback and inspect safety/readiness fields.

Events carry `schema_version`, `event_id`, `type`, `timestamp`, `session_id`,
`episode_id`, and `payload`:

| Event type | What to track |
| --- | --- |
| `snapshot`, `queue_update` | Status, queue position, episode, lease, and active trajectory |
| `lifecycle` | `payload.state` and transition reason |
| `observation` | Measured joints, grippers, timestamp, and images in `payload` |
| `trajectory_result` | Correlated packet `accepted`, `rejected`, `completed`, or `aborted` |
| `trajectory_progress` | Executed waypoint `step_id` for a trajectory |
| `heartbeat` | Gateway lease renewal; this is a server-to-client event |
| `episode`, `error` | Results or structured failures |

A new subscription starts with a snapshot and may replay the newest observation
and trajectory result (`payload.replayed: true`). It is not a complete event
history. Match episode, lease, trajectory, and step IDs; replayed state must not
trigger duplicate motion. Use observation pagination or the episode trace for
retained history. The next observation follows the last executed waypoint's ID.

The station gateway renews the lease; there is no client REST heartbeat route.
A closed WebSocket does not itself stop the session. On a connection failure,
pause command generation, reconnect to the same session, and reconcile its
snapshot/trace before continuing. Request Stop if you cannot recover safely.

### Send a trajectory

Send `POST /v1/sessions/{session_id}/trajectories` only after your session has
control and its previous packet has finished. The following illustrates the
**wire format only**. Its zero angles are placeholders, not a hardware motion
recipe. Compute targets from fresh feedback and the selected robot's profile.

```json
{
  "schema_version": 1,
  "episode_id": "ep_example",
  "lease_id": "lease_example",
  "trajectory_id": "trajectory_example_0",
  "cadence_hz": 10.0,
  "waypoints": [
    {
      "step_id": 0,
      "left_joints_deg": [0, 0, 0, 0, 0, 0],
      "right_joints_deg": [0, 0, 0, 0, 0, 0],
      "left_gripper": 0.5,
      "right_gripper": 0.5
    }
  ]
}
```

- Use finite degree values and the exact arm lengths for your robot. Independent
  grippers are optional, from `0` (closed) to `1` (open).
- Cadence is exactly `10.0` Hz. Each packet contains **1–300 waypoints**.
- Start waypoint IDs at `0`, keep them contiguous within a packet, and continue
  across packets. Only one packet may be active at a time.
- Give new packets unique trajectory IDs. Retrying requires the **same ID and
  identical body**. Changed content under an existing ID causes a conflict.
- The shared runner caps a session at 3,000 accepted waypoints. Server budgets
  can differ by deployment/session type. The live schema currently allows a
  wider step-ID range; that field range alone is not a guaranteed motion budget.
- Planning, inference, execution, and settling consume the run duration. A
  waypoint budget does not extend the deadline. Gateway limits still apply.

HTTP 202 with `accepted: true` means **dispatched**, not physically executed.
Follow the matching gateway acceptance and ordered progress, its final settled
measured observation, and `completed` result before planning another packet.
A rejection or abort requires reconciliation; an aborted packet may have moved
through some waypoints. Do not treat network failure as proof that no motion
occurred. The bundled controller performs these correlations and reconnect
recovery, including trace checks when progress events were missed.

The public wire API accepts joint trajectories. Cartesian targets and model tool
calls in the runner are converted locally; they are not separate public motion
endpoints. The old `/actions` route is rejected.

### Stop and retrieve results

`POST /v1/sessions/{session_id}/stop`, using the session capability and JSON:

```json
{"reason": "user_requested"}
```

Use `policy_complete` when your policy has finished. Stop also cancels a queued
session. A completed packet retains the session for your next model call; send
Stop when the task ends. There is no public `/done` route. Model-reported success
is not independent verification that the physical task succeeded.

A Stop response reports API session state; it is not independent confirmation of
physical Hold or a promise about a return-home path. Follow measured station
feedback. The gateway controls physical stopping/reset behavior.

Read `/episode` for metadata and `/episode/trace` for actions, measured
observations, progress/results, errors, and lifecycle. Observation pages accept
`after_step_id` (initially `-1`) and `limit` (1–100), and return `has_more` and
`next_after_step_id`. Trace retention is configurable, one hour after completion
by default in the server implementation. Check `available_until` and download
needed results promptly; an expired trace returns 410.

API traces are separate from model-conversation logs and recorded videos.
The runner saves local logs/recordings. Published recordings appear in
[Public-YAM-runs](https://huggingface.co/datasets/andlyu/Public-YAM-runs) and
[Public-MakerMods-SO101-runs](https://huggingface.co/datasets/andlyu/Public-MakerMods-SO101-runs)
where recording/upload is configured. A robot registration does not guarantee
recording or immediate video availability.

## Camera intrinsics and extrinsics


Camera calibration is available through public, read-only requests. No API key,
queue entry, or active session is required. Start with `GET /v1/robots`: robots
with calibration advertise `calibration_url` and `camera_poses_url`, relative to
the Session API origin. A robot without configured calibration returns `404`.

```bash
export BLUPE_API="https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com"
curl --fail-with-body "$BLUPE_API/v1/robots/yam-1/calibration"
curl --fail-with-body "$BLUPE_API/v1/robots/yam-1/camera-poses"
```

### Which parameters to use

The `/calibration` response has a `calibration_id` and a `cameras` object:

| Field | Meaning |
| --- | --- |
| `cameras.{top,left,right}.K` | 3×3 intrinsic matrix in pixels: `[[fx,0,cx],[0,fy,cy],[0,0,1]]` |
| `cameras.{top,left,right}.distortion` | Lens coefficients; read `distortion_model` and the response's `distortion_order` |
| `cameras.{top,left,right}.image_size` | `[width, height]` for these intrinsics; use the matching image resolution |
| `cameras.top.T_base_camera.left` | Fixed top-camera pose relative to the **left arm base** |
| `cameras.top.T_base_camera.right` | Fixed top-camera pose relative to the **right arm base** |
| `cameras.left.T_grasp_camera` | Fixed left-camera mount relative to the left gripper's grasp frame |
| `cameras.right.T_grasp_camera` | Fixed right-camera mount relative to the right gripper's grasp frame |
| `cameras.{top,left,right}.image_url` | Relative URL for the corresponding RGB JPEG |
| `quality` | Fit status, validation residuals, failures, and operator selection |

The left and right bases are different coordinate frames. Use `.left` when
planning for the left arm and `.right` for the right arm; do not average matrices
expressed in different bases. Each `T_base_camera` is a 4×4 matrix mapping a
camera-coordinate point to the named arm's base:

```text
[x_base, y_base, z_base, 1] = T_base_camera @ [x_camera, y_camera, z_camera, 1]
```

Matrices are nested row-major arrays and act on column vectors. Translations
are in **meters**. Camera optical axes are **x right, y down, z forward**;
arm-base axes are **x forward, y left, z up**. Read the returned
`transform_convention`, `camera_axes`, and `base_axes` with each calibration.

Read the returned distortion model. YAM packages support OpenCV Brown-Conrady
(`opencv_brown_conrady`, coefficients `[k1, k2, p1, p2, k3]`) and RealSense
factory profiles (`realsense_factory`, with `depth_intrinsics`). Account for distortion
when projecting or unprojecting pixels. Cropping or resizing an image requires
adjusting its intrinsics. Calibration maps a pixel to a ray; determining a 3D
point also requires depth, triangulation, or a known surface.

### Moving wrist cameras

`GET /v1/robots/yam-1/camera-poses` returns the current wrist extrinsics:

- `cameras.left.T_base_camera.left`: left wrist camera → left arm base.
- `cameras.right.T_base_camera.right`: right wrist camera → right arm base.

The API computes these from measured joints and the fixed mount:
`T_base_camera = T_base_grasp(measured_joints) @ T_grasp_camera`.
Refresh them after the arm moves. The response includes `joints_deg`,
`observed_at`, `age_s`, and the matching `calibration_id`; refetch calibration
if its ID changes. The static report also includes `kinematics` for clients
that need to reconstruct poses from recorded joint observations.

Pose requests require settled hardware feedback no more than two seconds old.
If feedback is absent, moving, stale, or simulated, the endpoint returns
`503` with error code `camera_pose_unavailable`. The static `/calibration`
endpoint still works when the arms are off. A failed pose request is not a
reason to reuse an earlier wrist pose as current.

Image capture and joint feedback are **not hardware synchronized**:
`camera-poses.synchronized_with_images` is `false`. Its `observed_at` is the
joint-feedback timestamp, while camera responses provide `X-Captured-At`.
Check both timestamps and use settled captures for geometric measurements.

### Python: retrieve calibration without moving the robot

This example uses only Python's standard library:

```python
import json
from urllib.error import HTTPError
from urllib.request import urlopen

API = "https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com"
ROBOT = "yam-1"


def get_json(path):
    with urlopen(API + path, timeout=10) as response:
        return json.load(response)


calibration = get_json(f"/v1/robots/{ROBOT}/calibration")
top = calibration["cameras"]["top"]
K = top["K"]
distortion = top["distortion"]
T_left_base_top = top["T_base_camera"]["left"]
T_right_base_top = top["T_base_camera"]["right"]
print("Calibration:", calibration["calibration_id"])
print("Top image size:", top["image_size"], "K:", K)
print("Fit quality:", calibration["quality"])

try:
    poses = get_json(f"/v1/robots/{ROBOT}/camera-poses")
except HTTPError as error:
    if error.code != 503:
        raise
    print("Current wrist poses unavailable:", error.read().decode())
else:
    if poses["calibration_id"] != calibration["calibration_id"]:
        raise RuntimeError("Calibration changed; fetch calibration and poses again")
    T_left_base_wrist = poses["cameras"]["left"]["T_base_camera"]["left"]
    T_right_base_wrist = poses["cameras"]["right"]["T_base_camera"]["right"]
    print("Joint feedback timestamp:", poses["observed_at"])
    print("Left wrist to left base:", T_left_base_wrist)
    print("Right wrist to right base:", T_right_base_wrist)
```

## RGB-D observations

Depth availability is **per camera**. Read its `depth` object in the calibration
response. `available` describes fresh data now; an advertised `on_demand: true`
URL can request a capture even when `available` is false. Prefer advertised URLs
over assuming every robot/camera supports depth.

| Representation | Contents and use |
| --- | --- |
| `depth.bundle_url` / `.rgbd.npz` | Paired RGB-D in `rgbd-npz-v1`: `rgb` uint8 H×W×3, `depth_m` float32 H×W, and scalar JSON `metadata` |
| `depth.native_bundle_url` / `.rgbd-native.zip` | Advertised `rgbd-jpeg-z16-png-v1` bundle with JPEG RGB, bit-exact sensor depth, and metadata |
| `depth.image_url` / `.depth.png` | 16-bit depth PNG in millimeters; separate RGB/depth requests may select different captures |
| `depth.raw_bundle_url` / `.rgbd-raw.npz` | Original-array download when advertised; use its separate age/transfer policy |
| `depth.request_url` / `.rgbd?compression=compressed` | Negotiated compressed/native representation, when advertised; `compression=none` selects the raw representation |

Legacy NPZ reads use `numpy.load(..., allow_pickle=False)`. Check camera/robot
identity, `calibration_id`, dimensions, and `captured_at`. Aligned depth measures
color-camera optical Z in **meters**; zero/NaN indicate missing measurements.
A surface point is not automatically a valid gripper target.

Missing or stale depth returns **204 No Content**, an empty body, and
`X-Camera-Error: no_image`; do not try to parse it as NPZ/PNG. Retry observation
reads within your run deadline and honor cancellation. RGB JPEG reads can return
**503** for missing fresh frames. Wrist-pose reads use their own 503 JSON error.
Unknown/unconfigured resources can return 404. Successful image/depth responses
carry capture timestamps; camera/calibration responses use `Cache-Control: no-store`.

The standard public depth freshness window is five seconds. The shared moving
policy applies a tighter two-second bound unless feedback confirms the robot is
stopped, and hardware policy captures must follow their settled-feedback cutoff.
Different cameras are not hardware synchronized. Check source timestamps rather
than substituting download time.

Inspect `quality.status`, `quality.failures`, and validation residuals before
relying on geometry. `operator_selected: true` records an experimental selection;
it does not turn a rejected or experimental fit into validated calibration.
See the [RGB-D contract](../codex-runner/docs/api-depth-contract.md),
[native bundle format](../codex-runner/docs/native-depth-contract.md), and
[Astra depth example](../codex-runner/docs/astra-depth-example.md).

## Endpoint reference

Paths are relative to the Session API origin. `sid` means your session ID.
Session HTTP and WebSocket routes require that session's Bearer capability.

| Method | Path | Access / purpose |
| --- | --- | --- |
| GET | `/health` | Public service health; not robot readiness |
| GET | `/v1/contracts` | Public JSON Schema bundle |
| GET | `/v1/robots` | Public registered robot IDs and calibration links |
| GET | `/v1/robots/{robot_id}/queue` | Public queue and station availability |
| GET | `/v1/queue?robot_id=yam-1` | Compatibility queue route; defaults to `yam-1` |
| GET | `/v1/robots/{robot_id}/observation` | Public latest station feedback and camera URLs |
| WS | `/v1/robots/{robot_id}/events` | Public station status stream |
| GET | `/v1/robots/{robot_id}/calibration` | Public static intrinsics/extrinsics and quality |
| GET | `/v1/robots/{robot_id}/camera-poses` | Public current poses from settled hardware feedback |
| GET | `/v1/robots/{robot_id}/cameras/{role}.jpg` | Public latest RGB JPEG |
| GET | `/v1/robots/{robot_id}/cameras/{role}.rgbd.npz` | Public paired RGB-D when configured |
| GET | `/v1/robots/{robot_id}/cameras/{role}.rgbd-native.zip` | Public native bundle when advertised |
| GET | `/v1/robots/{robot_id}/cameras/{role}.rgbd-raw.npz` | Public original arrays when advertised |
| GET | `/v1/robots/{robot_id}/cameras/{role}.rgbd?compression=compressed` | Public negotiated bundle when advertised |
| GET | `/v1/robots/{robot_id}/cameras/{role}.depth.png` | Public 16-bit depth PNG when configured |
| POST | `/v1/sessions` | Public session creation; requests a real queue entry |
| GET | `/v1/sessions/{sid}` | Session status, lease, and active trajectory |
| WS | `/v1/sessions/{sid}/events` | Session snapshots, observations, execution events |
| GET | `/v1/sessions/{sid}/observations?after_step_id=-1&limit=100` | Paginated retained observations |
| POST | `/v1/sessions/{sid}/trajectories` | Submit a joint trajectory; HTTP 202 |
| POST | `/v1/sessions/{sid}/stop` | Stop or cancel your session |
| GET | `/v1/sessions/{sid}/episode` | Episode metadata and retention |
| GET | `/v1/sessions/{sid}/episode/trace` | Retained execution trace |
| POST | `/v1/sessions/{sid}/public-conversation` | Replace or withdraw an opt-in public text snapshot |

The client retains a `call_operator()` helper, but the public router has no
`/operator` endpoint. Use Stop; the playground's Call Operator button displays
contact information. Station publisher/operator credentials and routes are
separate from this developer control API.

## Errors and retries

Session JSON errors use this envelope:

```json
{
  "error": {
    "code": "invalid_session_state",
    "message": "a trajectory is already active for this session",
    "status": 409
  }
}
```

Camera binary endpoints can return plain text or an empty body instead. Check
HTTP status and content type before decoding a response.

| Status | Meaning / response |
| --- | --- |
| 400 | Invalid fields, shape, values, or protocol version; correct the request |
| 403 | Missing/invalid capability, or invalid/expired episode or lease context |
| 404 | Unknown session, robot, route, or unconfigured resource |
| 409 | Invalid state, active packet, sequencing, or idempotency conflict; reconcile state |
| 410 | Retained episode data expired |
| 429 | Rate limit; respect the deployment's limits before retrying |
| 502 / 503 / 504 | Contact/service problem; execution state may be uncertain |

The bundled HTTP transport retries reads and stable-ID trajectory submissions up
to **three total attempts**, with 1- and 2-second pauses, for transient contact
failures. It does not automatically retry creation or Stop. It surfaces other
HTTP errors rather than blindly retrying them. The local server's default rate
budget is 900 accepted waypoints per minute; deployment hooks can change it.

After an uncertain dispatch, retain the original ID/body and inspect the session
and trace. Never assign a new ID just to retry the same motion. The controller
reconnects the same session and verifies missed completion against recorded
acceptance, ordered progress, and final feedback. A network failure does not
prove that a command was rejected or that no motion occurred.

## Python client and custom policies

The importable client lives in `codex-runner/src/remote_yam/session.py`.
From the repository root, this example performs only a public queue GET:

```bash
PYTHONPATH=codex-runner/src python3 - <<'PYTHON'
from remote_yam.session import HttpSessionAPI

api = HttpSessionAPI(
    "https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com",
    robot_id="yam-1",
    joint_counts=(6, 6),
    supports_trajectories=True,
)
queue = api.get_queue_snapshot()
print("Queued:", len(queue["entries"]))
print([(s["connected"], s["available"]) for s in queue["stations"]])
PYTHON
```

Set **`supports_trajectories=True` explicitly** for direct controller integration.
This is a client configuration switch, not automatic capability discovery. The
normal playground already enables it. Actual control also needs
`websocket-client`; the launcher installs the runner dependencies.

For a model integration, start with the [shared runner](../codex-runner/README.md)
and [provider interface](../codex-runner/src/remote_yam/providers.py). A provider's
`infer(prompt, observation)` returns a runner command for local IK; a
`build_trajectory(prompt, observation, first_step_id)` hook can supply waypoints.
[RunnerController](../codex-runner/src/remote_yam/controller.py) owns queue,
feedback, completion, retry/reconnect, and Stop handling.

Use the [Python transport](../codex-runner/src/remote_yam/session.py) for an
independent backend client. The ready-made UI has no arbitrary model-upload field.
The existing [depth example](../codex-runner/examples/astra_depth.py) shows a
concrete integration, with its own setup and qualification requirements.

## Custom end-point

Choose **Custom end-point** in the playground's model selector, then enter your
policy server's HTTPS base URL. The **Endpoint format and examples** link directly
below the field opens this guide. Enter an optional bearer key if your server
requires one. Selecting the option does not start a run; enter a task and choose
Run when ready. The URL stays in the current page when you switch models; the key
is cleared when you switch away and is not saved as a reusable provider key.

This option appears in the main model list for every available robot, including
the default Robo-house YAM. The runner sends the selected robot's measured joint
state and configured model cameras and executes validated action chunks; your
endpoint supplies inference. The contract uses the same units and chunk timing
as MolmoAct2, without requiring a particular checkpoint or GPU. Your endpoint
must support the selected robot's identity and joint layout.

### Custom server contract

Use a public HTTPS base URL on port 443, for example
`https://policy.example.com` or `https://policy.example.com/yam`. The runner appends
`/health` and `/act` to that base path. URLs cannot contain credentials, a query,
or a fragment. Private, loopback, link-local and other non-public IP addresses are
rejected at connection time; redirects are not followed. Endpoint calls happen
from the runner, so browser CORS headers are unnecessary.

`GET /health` must return HTTP 200 and a JSON object:

The following example is for YAM1. Replace `robot_id` with the selected robot's
ID and `action_dim` with its number of arm joints plus one gripper per present
arm. For example, a single SO101 has five joints and one gripper (`action_dim: 6`);
a bimanual SO101 has two five-joint arms and two grippers (`action_dim: 12`);
YAM has two six-joint arms and two grippers (`action_dim: 14`). The playground's
`POST /api/session` response exposes the exact selected layout in
`custom_endpoint_profile`: `robot_id`, `joint_counts` (left, right), `cameras`,
and `action_dim`. Use that identity in both health and action responses.

```json
{
  "ok": true,
  "robot_id": "yam-1",
  "action_dim": 14,
  "num_actions": 30,
  "action_units": "radians",
  "gripper_units": "normalized_0_closed_1_open"
}
```

Return `"ok": false` while loading. The runner waits for readiness before joining
the robot queue, for up to twenty minutes. `POST /act` receives the request shown
below and must return HTTP 200 with:

```json
{
  "robot_id": "yam-1",
  "action_units": "radians",
  "gripper_units": "normalized_0_closed_1_open",
  "actions": [["<14 numeric targets per row; exactly 30 rows>"]]
}
```

The action example is a shape placeholder, not a runnable response. Supply
**30 rows of `action_dim` finite numbers**, representing 30 Hz absolute targets:
left joint radians, left gripper, right joint radians, right gripper. Omit the
entire joint-and-gripper group for an absent arm. For YAM, each arm has six
joints; the example above therefore has 14 values per row. Grippers
must stay in `[0, 1]`. The runner takes rows 3, 6, …, 30 for 10 Hz execution,
converts joint radians to degrees, and retains the gateway's motion limits.
Invalid units, dimensions, values or grippers reject the entire chunk. Extra
metadata such as `model`, `revision` and `device` is allowed; this generic option
does not certify checkpoint identity. A server implementing the MolmoAct2
contract below also satisfies this format for YAM1.

`POST /act` receives `robot_id`, `instruction`, `state`, `images`, `action_units`
and `gripper_units`, as in the MolmoAct2 example below. `state` follows the same
joint-and-gripper order as an action row. `images` contains the camera names in
`custom_endpoint_profile.cameras`, each as a base64 RGB JPEG resized to 640 × 360.
The request always uses fresh measured state from the selected robot.

The optional key is sent as `Authorization: Bearer <your-key>` to both routes.
It belongs to your endpoint; the runner does not send its configured MolmoAct2
service key. Responses are limited to 8 MiB; health requests time out after 30
seconds and action requests after 12 seconds. Keep your server reachable and
warm enough for that action timeout. Run, Stop and queue controls use the normal
playground session, rather than a direct browser connection to the policy server.

### MolmoAct2 endpoint contract

The existing [YAMRunpodAdapter](../codex-runner/src/remote_yam/yam_runpod_policy.py)
uses an HTTPS base URL such as `https://<deployment>.api.runpod.ai`. It calls
`GET /health` and `POST /act`, sending `Authorization: Bearer <service-key>` to
both. The endpoint and key are runner configuration; keep the service key in a
private file on that machine. It is not a BluPe session capability.

For the existing **YAM1 MolmoAct2** adapter, `/health` returns:

```json
{
  "ok": true,
  "robot_id": "yam-1",
  "model": "allenai/MolmoAct2-BimanualYAM",
  "revision": "8dcbed66f2380e4393189c303ea72488eb9e63c2",
  "cuda_available": true,
  "device": "cuda:0",
  "action_dim": 14,
  "num_actions": 30,
  "norm_tag": "yam_dual_molmoact2",
  "action_units": "radians",
  "gripper_units": "normalized_0_closed_1_open"
}
```

The runner checks this identity and readiness before joining the robot queue.
GPU preparation happens before the robot run timer starts.

`POST /act` receives this object shape; angle and image values below are
illustrative placeholders for the fresh observation supplied by the runner:

```json
{
  "robot_id": "yam-1",
  "instruction": "Place the green block on the plate",
  "state": [0, 0, 0, 0, 0, 0, 0.5, 0, 0, 0, 0, 0, 0, 0.5],
  "images": {"top": "<base64 JPEG>", "left": "<base64 JPEG>", "right": "<base64 JPEG>"},
  "action_units": "radians",
  "gripper_units": "normalized_0_closed_1_open"
}
```

Each camera image is a base64-encoded RGB JPEG resized to **640 × 360**. State
order is **six left-arm joint radians, left gripper, six right-arm joint radians,
right gripper**. Grippers use `0` closed through `1` open.

The response repeats `robot_id`, `model`, `revision`, `device`, `action_units`
and `gripper_units` from the health identity, plus `actions`: exactly **30 rows
of 14 finite numbers** in the same arm/gripper order. Targets are absolute arm
radians with normalized grippers at 30 Hz. The runner selects every third target
for the Session API's 10 Hz trajectory and converts arm angles to degrees.
It rejects mismatched identities, units, dimensions and out-of-range MolmoAct2
grippers before dispatch.

In an existing YAM1 runner deployment, supply these constructor settings:

```python
runpod_key_file="/private/path/to/policy-service-key",
runpod_config={
    "molmoact2": {"endpoint": "https://<deployment>.api.runpod.ai"}
},
```

These are `HostedRunner` configuration arguments for the service-owned model,
separate from the visitor-owned **Custom end-point** fields. The configured MolmoAct2 adapter currently accepts RunPod hostnames and
the pinned checkpoint above on `yam-1`. DreamZero uses the same transport with
its own identity, normalization tag and 24-action horizon; do not substitute its
contract for MolmoAct2's.

### Other custom policies

For a different action format, horizon or robot, implement the runner's provider interface
and register it through `HostedRunner(extra_providers=...)`, following the
existing configured adapters. A `build_trajectory(prompt, observation,
first_step_id)` implementation returns Session API waypoints; an
`infer(prompt, observation)` implementation returns a runner command for local
IK. Retain the controller's observation and execution-feedback loop.

Browser-supplied `endpoint` values are accepted only for the `custom_endpoint`
provider with the contract above; other providers retain service-owned endpoints.
For additional protocols, use the [shared runner](../codex-runner/README.md), the
[provider interface](../codex-runner/src/remote_yam/providers.py) and
[MolmoAct2 adapter](../codex-runner/src/remote_yam/yam_runpod_policy.py) as the
implementation references. Model-server radians are distinct from the public
Session API's degree-valued trajectories described above.

### Local runner API and configured execution

Runner `/api/*` routes belong to the process you launch, not to the public Session
API. They use a visitor cookie and `X-YAM-Runner-Token` CSRF value from
`POST /api/session`. Run/status/Stop clients must retain the same visitor.
[RunnerPolicyClient](../codex-runner/src/remote_yam/runner_policy_client.py)
implements this for configured policies. See [environment resets](../codex-runner/docs/resets.md)
for supported configuration and current physical qualification.

There is no generic public `/v1/reset` route. The server source also implements
lease-bound `/v1/sessions/{sid}/executions` and result reads for specific installed
executors. These are deployment-specific extensions, absent from the public JSON
Schema bundle; confirm the installed executor and contract before using them.
They do not accept arbitrary uploaded policy code.

## Public data and conversation sharing

Robot recordings and published task information can be public. Keep private
context out of tasks and opt-in shared text. Recording/upload behavior depends
on the selected station and runner.

Direct API clients opt into readable model-message publication explicitly.
Omitting `public_conversation` does not publish a model conversation. To share
one, use the session capability with `POST /v1/sessions/{sid}/public-conversation`:

```json
{
  "public_conversation": {
    "model": "My model",
    "messages": [
      {"role": "user", "content": "Stack the blocks"},
      {"role": "assistant", "content": "Picking up the green block."}
    ]
  }
}
```

Each snapshot replaces the previous one; retries do not append duplicate
messages. Assigned sessions can appear as `public_run` in the robot queue
response. Limits are 64 messages, 8,000 characters per message, 64,000 total
characters, and an 80-character model label. Roles are `user`, `assistant`,
`tool`, `system`, or `developer`. Send `{"public_conversation": null}` to withdraw
the snapshot. Never include credentials, private history, raw provider payloads,
or image bytes.

The local playground enables sharing by default. Uncheck **Share conversation on
the public playground** before Run, or launch with `--no-share-conversation`, to
keep those messages local. This does not disable robot recordings or remove task
information already published through the playground/archive. Raw local model
logs and the opt-in public plain-text snapshot are separate artifacts.
