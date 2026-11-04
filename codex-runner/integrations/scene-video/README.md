# Forward scene video

Both YAM-1 arms advance 12 cm over 12 seconds while preserving their measured
wrist attitude and gripper fractions. The calibrated wrist optical axes must
point down over the tabletop throughout the route. This is a deterministic IK
capture method, with no foundation model or policy inference.

**Current status: incomplete.** The initial normal-playground physical run
`ep_11d0dcff60b448ba` executed 120 waypoints, then hit a local completion-check
bug. That check is repaired and covered offline. Raw images and feedback are
durably saved; the observer-only quick preview is available. The full retained
wrist-camera movie, dataset publication and final normal-UI acceptance are still
open. See the [working checklist](docs/COMPLETION-CHECKLIST.md). A quick preview
does not establish complete scene capture, synchronization or training quality.

## Reproduce the offline gate

Use the shared runner at `7ba2427ba960ad30af99c8fedd05c5196685295a` and the public
controller at `d1f9e8d588b18810d13c0edbe34646763dc8f257`. Check out those revisions
in separate directories; existing working changes need not be moved. Their
public repositories are [blupe-remote-bots](https://github.com/andlyu/blupe-remote-bots)
and [blupe-playground-robot-controller](https://github.com/andlyu/blupe-playground-robot-controller).
The controller's runtime is `src/blupe_controller/runtime`.

Install the runner requirements plus NumPy, SciPy, OpenCV and pytest in a Python
environment. FFmpeg is required. On a headless Linux host use OSMesa and
`MUJOCO_GL=osmesa`; macOS rendering needs normal CoreGraphics access.

```sh
python codex-runner/integrations/scene-video/run.py verify \
  --runner-root /path/to/pinned-runner/codex-runner \
  --hardware-root /path/to/pinned-controller/src/blupe_controller/runtime \
  --output /path/to/scene-video-evidence
```

This command sends no physical command. It runs completion regressions, generates
the actual fixed route, exercises the canonical serializer/validator with a wire
spy, tests fractional held grippers/endpoints/invalid zero-dispatch cases, checks
camera geometry and a collision-enabled controller snapshot, and renders and
decodes/seeks a labelled three-view simulation MP4. The final receipt retains
source/calibration/validator hashes and separate command runtimes. The live
station's gateway guards remain mandatory for every physical packet.

The `Forward scene video preflight` GitHub Actions job runs this gate. A release
must retain a passing receipt for the exact policy source, verify the matching
calibration and run the existing hardware queue/lease path. Changing control code
reopens physical acceptance; offline passes never certify physical capture.

## Connect after simulation verification

```sh
python codex-runner/integrations/scene-video/run.py serve \
  --runner-root /path/to/pinned-runner/codex-runner \
  --output /path/to/scene-video-evidence --port 8796
```

Open `http://127.0.0.1:8796/`. Use normal Run setup with the actual runner's editable
name/email. The fixed method uses a 60-second maximum admitted session, normal
queue/readiness/startup Home, real packet validation and Stop. No API key is
needed. The policy plans from fresh leased measured Home feedback; it never
replays saved simulation joint targets. A changed camera calibration or policy
source rejects launch until verification is repeated. Completion keeps the
existing controller's 0.05 rad measured joint tolerance; this does not change
hardware limits or settling checks. Never replay an uncertain/timed-out move.

The station retains this method's camera/feedback recording in its existing
dataset workflow. Match replay and dataset artifacts to the exact episode ID;
wait for real publication and verify playback/seek. Preserve missing-frame and
quality labels. The [harness authorization contract](docs/BLUPE-HARNESS-CONTRACT.md)
and [control contract](docs/CONTROL-CONTRACT.md) apply; fill in actual scope before
physical side effects. Do not claim integration completion while checklist items
remain open.
