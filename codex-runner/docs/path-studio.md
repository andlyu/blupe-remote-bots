# Bimanual YAM Path Studio

Draw a 3D line or enter **Draw a heart**, then choose **Simulation · real
constraints** or **Real arms · API** at http://127.0.0.1:8916/.

```bash
python3.12 -m venv .venv-path-studio
.venv-path-studio/bin/pip install -r codex-runner/path-studio-requirements.txt
./run-path-studio.sh --port 8916
```

Both modes use this standalone local bridge. WebGL is required. The shape
vocabulary is built in: heart, star, circle, square, triangle and infinity.
No language-model API key is needed.

## Verify in simulation

Choose Simulation and press **Verify & draw**, or draw/edit a path and press
**Verify & play**. The entire motion must pass before playback begins.

Simulation runs the same Python `PathStudioPolicy` used for physical execution,
with isolated simulated feedback. It reads station calibration without creating
a control session or issuing motor commands. The displayed 10 Hz joint frames
are the policy's actual packets, with the station's encoder offsets applied once
for rendering. Together mode starts left at the notch and right at the bottom of a heart,
then traces the two halves simultaneously at shared progress. The arms finish at
opposite endpoints. Take turns remains available for sequential exact strokes. Alignment, approach,
closure, endpoint holds and retreat are part of playback. Only drawing phases
leave a cyan/pink trace. Pause, scrub, replay and Save verification are available.

Together mode keeps at least **20 mm of modeled gripper surface clearance**.
It tries the desired paired poses first. When they collide or lose clearance, a
bounded search finds the smallest feasible symmetric outward-Y adjustment along
that search direction (within 0.5 mm resolution, capped at 100 mm per arm).
This is not a claim of a global spatial optimum. All adjusted targets and full
joint sweeps must still pass arm, gripper, table, workspace and pacing checks.
If no valid complete plan is found, playback/control is blocked before motion.
The preview reports minimum mesh gap and maximum outline deviation and renders
the effective tool strokes against the desired outline. For the standard heart,
opposite traversal directions avoid the shared-endpoint conflict without any
intentional outline adjustment.

The shared checks cover:

- Station/model calibration binding, saved controller workspace and joint limits.
- Forward, level tools, with right wrist rolled 90° for housing clearance.
- Gripper closure while holding arm joints, followed by closed feedback.
- Original arm, installed I2RT housing/finger CAD, nominal table and joint sweeps
  at ≤0.01 rad intervals, with a modeled clearance margin.
- Cartesian speed, ≤0.035 rad joint steps, normalized gripper steps ≤0.1.
- 10 Hz packets, ≤300 waypoints per packet and ≤3,000 per session.
- Sequential tracking within 3 mm / 0.035 rad. Together allows 25 mm / 0.08 rad of measured target error only after validating measured encoders, closed jaws and the same 20 mm CAD gripper gap. Each next packet rebases and retimes from that measured state.

The reproducible reference start is `[-.024, .794, .645, -.375, -.021, -.012]`
radians for each arm, with grippers fully open. It is explicitly a reference pose,
not a reading of the physical station. **Real execution replans from measured
joints.** Both modes use API base spacing: currently Robo-house **620 mm**, YAM1
**500 mm**. The earlier 600 mm Robo-house visual preset is superseded in this
verification mode so the modeled dimensions agree with real planning.

The verification receipt identifies its start state, calibration source, saved
controller profile, packet sizes, CAD sample count and numerical tracking error.
A report without live controller safety hashes cannot verify the deployed safety
configuration; the saved profile is still checked and hardware gateway admission
remains required. Simulation is kinematic: it does not reproduce actuator
tracking, load, dynamics, movable objects or the entire physical scene.

## Real arms through the API

Opening Real arms reads measured joints, calibration, queue state, three detail
cameras and an expandable observer. Robo-house uses the public composite HLS
observer tile; YAM1 uses observer JPEG. Unknown gripper readings are labeled
unknown, with finger meshes hidden instead of displaying an invented opening.

Create path never moves hardware. **Run on real arms** explicitly joins the API
queue. Queue identity is editable in the API panel
and saved in ignored `.local/path-studio-identity.json`. Identity does not enable
video emails. The API queue performs the normal station startup when admitted;
an idle disabled status alone does not mean a queue-ready station is unavailable.

The runner validates the whole path from fresh measured joints before the first
packet, closes the selected grippers separately, requires measured closure,
then aligns and approaches. Both arms follow the selected coordination. Together plans keep their
gripper meshes separated while allowing the documented bounded outline adjustment. An unselected arm remains at its measured joints.

Packets retain contiguous IDs, idempotent retries, episode/lease correlation,
gateway validation and final measured feedback. Startup requires homed; later
packets require fresh settled feedback and consistent station safety. Rejections
or controller-adjusted paths stop the run. **Stop** cancels your session; a failed
acknowledgement stays visible and prevents another run until retried.

### Alignment completion and tracking

The recorded physical attempt closed both grippers, then stopped before any
heart stroke: the first alignment packet was reported complete while the left
tool was 14.292 mm from its target. The controller's 0.1 rad joint completion
tolerance is looser than the studio's 3 mm Cartesian tracking requirement.

Packets now hold their final target for 0.5 seconds. A small error during alignment,
approach or retreat may trigger at most two same-target settling retries, each
rebuilt from fresh measured joints with the same limits and swept CAD checks.
No drawing cursor advances until pose agreement passes. In sequential mode, errors must improve and drawing-stroke errors still stop.
Together treats the outline as approximate: safe measured target errors up to
25 mm are accepted; larger errors still stop. Measured gripper clearance, jaw
closure, joint limits and gateway checks remain mandatory. The recorded
feedback is retained as a regression fixture. This corrects the premature
alignment abort path without changing motor gains; Together intentionally permits the documented tracking approximation.
The physical robot must still demonstrate the required tracking.

## Model and editor

The rendered arms use the exact controller URDF chain and original STL meshes,
plus the installed I2RT linear_4310 gripper CAD. Source snapshots and SHA-256
provenance live in `models/controller-yam/`. The model bundle is generated by
`scripts/build_path_studio_model.py`. Each arm renders nine mesh instances;
finger slide travel is 0.0475 m per finger at normalized opening 1.

Draw on XY/XZ/YZ planes, change the fixed coordinate to add depth, or edit XYZ
fields in millimetres. Orbit rotates/pans/zooms; Front and Top align the view.
Import/export accepts 2–2,000 finite XYZ points in the common YAM frame in metres,
plus station, arm assignment and speed metadata. Browser storage saves the sketch.
Exported geometry is not a hardware command packet. Editing a path or speed
invalidates its previous simulation verification.

## Local isolation and development

The service binds to loopback, checks Host/Origin and a local CSRF token, and
proxies fixed camera/video routes only. BluPe capabilities remain in backend
memory. Closing the server attempts to stop its own active session. Verification
never creates a control session. Hardware control is available only through Run.

```bash
node --test codex-runner/tests/test_path_studio.cjs
PYTHONPATH=codex-runner/src .venv-path-studio/bin/python -m pytest -q \
  codex-runner/tests/test_path_studio_api.py \
  codex-runner/tests/test_trajectory_transport.py \
  codex-runner/tests/test_final_position_recovery.py
```

Tests cover both-station simultaneous heart packets, independent swept mesh gap
checks, a collision-forcing short-stroke approximation, exact simulation/real-policy parity,
recorded tracking residual recovery, persistent-error stops, collision positives,
transport/lease/stop behavior and local HTTP security. Mock execution is separate
from physical success. Per-run geometry, initial measurements and preflight
journals are retained in ignored `.local/path-studio-runs/` for diagnosis.

Three.js 0.180.0, OrbitControls, STLLoader and HLS are bundled locally. Manufacturer
and library licenses are retained. See the root API.md and CONTROLLER-WORKSPACE.md
for transport and saved controller profile details.

## Private hosted deployment

The default launcher remains loopback-only. For a single owner's deployment,
configure `PATH_STUDIO_PUBLIC_ORIGIN` with the exact HTTPS origin,
`PATH_STUDIO_USERNAME`, and a `PATH_STUDIO_PASSWORD` of at least 24 characters.
`PATH_STUDIO_BIND=0.0.0.0` and `PORT` support container ingress behind the host's
TLS termination. Public binding without those explicit settings is refused.
Host matching and HTTPS-origin CSRF checks do not trust forwarded headers.
The sign-in form issues a Secure, HttpOnly, SameSite=Strict owner cookie. HTTP
Basic authentication is also supported for automated checks. All workspace
assets and APIs require owner authentication; the sign-in stylesheet and
`/healthz` are public. `/healthz` returns only
`{"status":"ok"}` for platform checks. Do not expose the container's unencrypted
HTTP port directly on the internet.

Use one process and one instance: this is a private owner controller with shared
run state and identity. A public multi-user product needs isolated visitor
controllers and identities. `PATH_STUDIO_STATE_DIR` selects the private identity
and run-receipt directory; otherwise the local `.local` location is retained.
Back it up or retain receipts separately when deploying on ephemeral storage.
SIGTERM requests the normal service shutdown and Stop before closing the server.
Do not redeploy during an active robot session.

On October 26, 2026, the real Robo-house API completed the synchronized heart:
248/248 shared drawing steps, 386/386 target samples and 10/10 packets, with a
maximum measured packet-end TCP error of 14.78 mm and minimum checked CAD gripper
gap of 59.66 mm. This was an air drawing without a pen. Earlier failed alignment
attempts documented above are historical. Kinematic verification does not
establish accuracy for a different start state, payload or physical scene.

The UI supports a reverse-proxy mount such as `/path-studio/`. Keep the trailing
slash on the entry URL, set `PATH_STUDIO_BASE_PATH=/path-studio/` to scope the
owner cookie and sign-in redirect, and strip that prefix before forwarding to the Python
service. Assets, JSON requests and observer streams resolve within the same
mount, including the owner's browser authentication scope. Configure the public
origin without the path (`https://playground.blupe.io` for that deployment).
