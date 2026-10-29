# Dream One on the controller

The existing `DreamAdapter` can run on the controller host as well as in a local
or hosted runner. Both instances share the same RGB encoding, SDK worker,
episode/window handling and action conversion. Inference stays at Dream Labs;
only input acquisition, the SDK and trajectory conversion move to the controller.

`remote_yam.controller_dream.NativeControllerDream` binds an instance directly to
the existing YAM operator. Its observation callback reads the native snapshot and
local camera references in that process. `predict(prompt)` retains one result for
the current session/episode/lease. `submit()` consumes that result once through
the existing `api_handle_joint_trajectory`; it never calls a motor driver itself.
Stop, authorization loss or a changed lease discards the result. The caller must
use the existing Home/readiness lifecycle and forward the existing trajectory
completed/adjusted/failed callbacks. A prepared `DreamWorkerPool.factory` can be
passed as `worker_factory`, retaining the existing both-form SDK preparation.

`controller_dream_executor.install(hardware, **settings)` composes the binding
after the installed operator's calibration/recovery wrappers. Settings are
operator configuration, never request-supplied paths or credentials. Its SDK
pool prepares in the background without opening hardware. The existing native
prepare hook retains the session task, duration and lease. The policy loop uses
native trajectory validation, ordered progress and settled completion feedback;
workspace replacements/holds are returned to the same Dream adapter. Stop and
lease loss cancel immediately, without waiting for the model or SDK cleanup.
Only receipts for these local trajectories are consumed in process; existing
observations, heartbeats, recording and station messages retain their transport.

## Optional request routing

Add `"executor": "dream_one"` to the existing Playground `/api/run` request for
RoboHouse with provider `dream` and model `dreamlabs/dream-1-beta`. Every other
field stays the same. An omitted executor or JSON `null` constructs the existing
runner provider and makes no execution-start request.

```json
{
  "provider": "dream",
  "model": "dreamlabs/dream-1-beta",
  "prompt": "Move the block into the tray.",
  "run_duration_s": 120,
  "executor": "dream_one"
}
```

The runner joins the same queue and waits for the normal Home/readiness flow.
It then uses the existing session capability and execution envelope:

```http
POST /v1/sessions/{session_id}/executions
Authorization: Bearer {existing_session_capability}
Content-Type: application/json

{"schema_version":1,"episode_id":"{episode_id}","lease_id":"{lease_id}","request_id":"{32_lowercase_hex_chars}","executor":"dream_one","operation":"start","payload":{}}
```

Poll the existing `/executions/{request_id}` response for completion. `start`
acknowledges loop startup rather than waiting for the full task. Further `status`
requests use fresh request IDs and return bounded phase/count/readiness metadata.
`predict` runs one converted prediction with zero native submissions; use a
separate lease for this diagnostic. The controller always takes the task from
`prepare_session`; it rejects alternate prompts, motion targets and SDK settings
in the execution payload. A lease cannot mix Dream with another executor.
Repeated start requests for the same lease never create a second loop. The
existing session Stop endpoint remains the cancellation path.

The low-level execution endpoint requires a named executor. The omitted/null
default belongs to the run request/caller, which skips this endpoint entirely.
Installing shared code alone does not activate a station; the Session API must
allow the executor and the operator must install its hook before use.

## No-motion controller probe

`tools/probe_controller_dream.py` runs on the controller host and exposes no
command transport. It reads only the existing loopback physical operator status
and camera relay. The deployed status endpoint reads a fresh native snapshot in
physical STOPPED/EXECUTING states, including operator mode API_ACTIVE. The probe
accepts active-session telemetry without changing its queue or ownership. It
rejects DISABLED display-cache joints, absent grippers, faults and another robot
identity. Its observation time is the conservative
start of the HTTP snapshot bracket, explicitly recorded as such.

Prepare the pinned SDK in a separate Python 3.12 environment using
`requirements-dream.txt`. For the existing deployment's numerical implementation,
retain `YAM_DREAM_BLOCKWISE_IK=1` and the pinned JAX/JAXlib 0.7.1. Credentials remain
in a private controller-owned file. This uses CPU for the SDK's local IK; the
model is remote, so no local inference GPU is required.

```sh
YAM_DREAM_BLOCKWISE_IK=1 /path/to/sdk/bin/python tools/probe_controller_dream.py \
  --config /path/to/controller/profile.json \
  --credentials /path/to/private/dream/credentials \
  --sdk-python /path/to/sdk/bin/python \
  --work-dir /path/to/private/probe-output
```

The neutral default prompt is `Hold the current pose.` The probe prepares both
SDK checkpoints with synthetic inputs, then makes at most three beta requests
(including provider-warming replies), stopping after one converted prediction.
`--max-requests 1` selects a strict single-call diagnostic. It converts and
validates the result without submission. A private
receipt contains input source/timing, camera hashes/timestamps, SDK timing,
waypoint counts and zero submitted commands. It contains no credential, prompt,
raw image/state or waypoint arrays. Physical task performance, lease admission,
Home and dispatch need separate normal-run validation.

Video publishing/player and recording/dataset capture/export are not touched.
