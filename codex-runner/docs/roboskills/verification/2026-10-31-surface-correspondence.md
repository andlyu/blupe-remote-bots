# RoboSkills cross-view surface correspondence

The current physical run7f23d80e reached its above-block approach within the
existing3mm/2degree settling limits, then stopped before contact after comparing
different overhead/wrist surface samples. Full stacking is still unverified;
the current acceptance audit remains12/15 with7,13,15 open.

The retained Top31083 point projects to Right318.68,231.26, rather than the
agent-selected340250. The archived nearest-ray patch is15.93mm nearer than the
model prediction. The reverse selected wrist point projects to the top image's
object edge, with a24.78mm farther patch. These observations can reflect
occlusion, edges, depth error or model error. They do not establish calibration
accuracy or justify changing the calibration. The original factory-rectified
profiles, fitted wrist mounts and native joint calibration match the active
report; separate board-fit RGB intrinsics are not the metric transform source.

The candidate exposes `bot.project_point(point_base_m, arm=..., camera=...)`
against the current captured view. It returns the model pixel/optical depth,
optional nearest-ray radius2 depth patch, signed raw residual, capture identity
and calibration uncertainty. It neither captures nor submits motion. Outside
pixels are not clamped; missing/noisy depth remains unavailable. The1nm camera
near-plane guard and normalized-ray convergence tolerances are arithmetic
guards, not changed physical limits or accuracy claims.

The last four distinct pixel queries also appear automatically alongside the
next captured images, retaining their source camera/pixel/step/time. These are
explicitly historical, untracked surface references. Movement invalidates the
projected views, and episode/lease changes clear the history. Existing acquisition
freshness, measured-pose binding, calibration identity, Stop and terminal
uncertain-motion behavior remain enforced. Original cached-query semantics are
preserved: a query describes the captured surface, not a new camera capture.

Two samples with only an optional tool ignored it. With automatic references,
two low-reasoning samples still selected an oversized color mask or a depth hole.
Two medium samples instead selected valid gray block-face and table depths;
their source-generation times were22.09s and24.27s. Subsequent effort changes to
medium, while initial effort remains none. This small archived-scene result
does not establish reliability, physical grasp accuracy or full-task execution
within300s. An initial-none sample from the earlier812bf9 startup context took
6.187s and selected the requested marked pixels; it was not physically executed.

Validation:

- New projection/lifecycle suite:12tests,78subtests,0.65s. The pre-feature
  regression run failed47checks and passed5 in0.56s.
- Full current candidate:1402passed,3skipped,426subtests passed in88.07s using
  the existing Python3.13 pinned runtime and isolated test-only OpenCV4.10.0.84.
- Tests cover the pinned RealSense2.58.1 SDK ray oracle, actual archived depth
  patches, all cameras/both base frames, endpoints/outside pixels, invalid input,
  depth holes, source/lease lifecycle, immutability, Stop and zero dispatch.
- Actual upstream Repl executed both generated medium programs against static
  archived RGB-D with no actuator transport. Both selected valid measured data.
- One already-generated continuation produced one four-waypoint native yam-1
  packet through actual IK, native bounds/pacing and canonical HTTP serialization.
  HTTP was mocked and execution stopped before transport. This was above-object
  alignment, not grasp/contact or physical success. The initial offline fixture
  origin-tag error and omitted persistent variable were evaluator defects and
  are explicitly retained in the evidence, not classified as robot failures.

The [sanitized model/SDK evidence](2026-10-31-surface-correspondence-offline.json)
retains generated programs, timings, limitations and local gate results. Required
push/PR CI, immutable runtime deployment and a fresh normal-UI physical task are
still pending. No source change bypasses native queue/readiness/validation,
motion bounds or uncertain-motion non-replay. The specifically excluded old
recording is not used.
