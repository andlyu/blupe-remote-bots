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

This is an internal adapter binding, without an execution service or public
model-routing API. It does not install itself into a station's run selection.
The existing runner instance and Session API route continue independently.

## No-motion controller probe

`tools/probe_controller_dream.py` runs on the controller host and exposes no
command transport. It reads only the existing loopback physical operator status
and camera relay. The status endpoint reads a fresh native snapshot in READY or
STOPPED; the probe rejects DISABLED display-cache joints, absent grippers, another
robot identity and an active session. Its observation time is the conservative
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
SDK checkpoints with synthetic inputs, then makes at most one real beta
prediction. It converts and validates the result without submission. A private
receipt contains input source/timing, camera hashes/timestamps, SDK timing,
waypoint counts and zero submitted commands. It contains no credential, prompt,
raw image/state or waypoint arrays. Physical task performance, lease admission,
Home and dispatch need separate normal-run validation.

Video publishing/player and recording/dataset capture/export are not touched.
