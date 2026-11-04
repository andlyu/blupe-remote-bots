# One-minute scene video

Both YAM-1 wrist cameras advance, move sideways and change aim across the shared
scene. The planned trajectory is 60 seconds: 600 points at 10 Hz in two validated
300-point packets. Grippers hold their initial measured fractions. This is
deterministic calibrated IK with no model inference or GPU startup.

One normal playground UI run completed all 600 points, with both packets accepted
and settled. Hardware pacing and settling produced 73.81 seconds of reported
execution and an 84.6-second full recording. The episode retained 844 samples and
2,991 images, with zero capture errors, one missed capture tick and 812 aligned
training-valid rows. The full movie retains two ticks with missing imagery and
labels held frames. Both arms parked with torque disabled; no movement retry.

- [Physical scene movie](https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/videos/ep_47151c9fe197419d.mp4)
- [Motion design](docs/ONE-MINUTE-SIMULATION.md)
- [Physical evidence](docs/evidence/minute-physical.json)
- [Launch preflight](docs/evidence/minute-launch-preflight.json)
- [Working harness checklist](docs/COMPLETION-CHECKLIST.md)

The capture task executed. Broader harness certification remains incomplete:
continuous timed UI screen recording, public deployment of this specific launch
page and remaining checklist-wide acceptance are not claimed. A saved video does
not certify reconstruction accuracy or complete physical scene coverage.

## Verify and launch

Use the shared runner at `7ba2427ba960ad30af99c8fedd05c5196685295a` and public
controller runtime at `d1f9e8d588b18810d13c0edbe34646763dc8f257` in separate
checkouts. `minute.py` checks pinned file hashes before verifying and serving.
Install the runner requirements plus NumPy, SciPy, OpenCV and pytest. FFmpeg is
required. Headless Linux uses OSMesa and `MUJOCO_GL=osmesa`; macOS needs normal
CoreGraphics access.

```sh
python codex-runner/integrations/scene-video/minute.py verify \
  --runner-root /path/to/pinned-runner/codex-runner \
  --hardware-root /path/to/pinned-controller/src/blupe_controller/runtime \
  --output /path/to/capture-evidence

python codex-runner/integrations/scene-video/minute.py serve \
  --runner-root /path/to/pinned-runner/codex-runner \
  --hardware-root /path/to/pinned-controller/src/blupe_controller/runtime \
  --output /path/to/capture-evidence --port 8797
```

Open `http://127.0.0.1:8797/`. Confirm the actual runner's editable name and email,
then use normal Run. An optional private `--identity-file` containing `name` and
`email` prefills those editable local fields. Never commit that file. The method
uses a 120-second maximum session allowance for Home/setup plus capture and stops
on completion. Queue/lease, fresh measured feedback, Home, hardware limits,
collision validation, Stop and normal release remain enabled. Never replay an
uncertain or timed-out movement.

The required preflight runs 25 regressions and generates the real route. It tests
both serialized packets, fractional grippers, numeric endpoints, invalid starts
with zero dispatch, fresh chunk joins, completion cursors and Stop. It applies
the controller snapshot guard, renders 600 frames and verifies decoding/seeking.
The launch factory binds that receipt to the exact motion source and calibration.
The GitHub Actions scene-video job uses the same preflight.

The older 12-second experiment remains in `scene_video.py` and `run.py` as history;
it is not the current minute entry point. Its earlier capture had gaps and a
completion-check bug, repaired before this minute run. The current run's saved
outcome is `policy_complete`; historical results are preserved.
