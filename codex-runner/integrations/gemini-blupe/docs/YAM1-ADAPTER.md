# YAM1 adapter — engineering evidence, physical qualification open

The production API remains e075e8d3 with the earlier single-arm image and
depleted Google credits. The new common bimanual runtime is packaged pending
restoration of existing SSH access. Physical Run remains unavailable.

`backend/yam1_scene.py` composes the hash-pinned canonical arm geometry with
the captured installed linear4310 fingers. Both arm roots and base visuals
use the saved0.50m spacing. Native angle corrections are already applied;
no second offset is added. Six arm joints and two coupled finger slides per
arm produce16qpos. Every index is looked up by name. The right arm starts at
qpos8 after adding left fingers, rather than the old rigid-tool qpos6.

`backend/yam1_kinematics.py` calls Google's unchanged generic `solve_site_ik`
from Robotics plugin9cb7f624 on this exact model, with native calibrated
limits and full other-arm/finger context. It independently checks achieved
position and rotation because the published solver's best-effort fallback
can return without satisfying orientation. This adapter does not substitute
RoboHarness's separate planning policy or additional movement restrictions.

The saved calibration fixture is a sanitized offline snapshot of YAM1
calibration9773d518, native-joint calibration6b24647a. It retains provisional
extrinsic accuracy and assumed base spacing. The three pinhole cameras match
its K/transforms (OpenCV+Z forward converted to MuJoCo-Z forward); original
Brown distortion is not rendered. This fixture is not a live-state source.

Arm visuals still lack qualified collision shapes and finger meshes use
convex contacts. Arm dynamics are the canonical nominal PD/inertial model;
finger gains are Google's published YAM Pro simulation assumptions. No cube
or manipulation success is claimed. The visible support plane does not
change the native guard's separate table/workspace frame or limits.

## Generated controller boundary

`controller_entry.py` runs `controller.py:run(env)` inside a keyless, network-
disabled rootless container. `yam1_environment.py` exposes `env.left` and
`env.right`: measured q_arm radians, normalized gripper, move_joint and Google's
IK. It adapts the DeviceLayer protocol/keys to the bimanual native geometry;
it is not the stock single-YAM-Pro PlaygroundSim2Real baseline.

`controller_channel.py` bounds JSON/diagnostics and preserves the original
deadline. `controller_bridge.py` supplies the canonical RunnerController
provider, compiles complete packets before dispatch, returns a local rejection
as proven-not-dispatched, and requires fresh reconciled feedback before an
explicitly revised request. Completion is sent to generated code only after
the canonical controller's matching settled completion. Unknown cursors,
timeouts, safety stops and unknown execution outcomes are never replayed.
No queue capability, private human contact, model key or CAN device is given
to the generated code. Runtime startup can precede queue/Home through the
existing prepare_before_session hook; its time still counts from original Run.

Actual rootless stdio proof: two packets/four waypoints, exact close0/open1,
1.301s ready/1.316s protocol wall. The handwritten controller and host serializer
used a zero-network transport spy, not physical feedback. Real RunnerController
mock-station tests separately cover local rejection/revision, measured completion,
Stop discarding late commands, unknown operations/cursors and failure non-replay.
Neither is a physical/native-contact qualification.

## Required development checks

Use the isolated Python3.12 MuJoCo4/Google Playground environment, plus backend
requirements. Keep the production native controller's MuJoCo version separate.
Set GEMINI_SKILLS_ROOT to the pinned plugin's `plugins/robotics/skills` directory:

```sh
python tools/preflight.py --runner-root ../.. --skills-root /path/to/pinned/skills --receipt /tmp/gemini-preflight.json
```

This required gate fails if geometry, Google IK or bridge coverage disappears.
It runs no network, model or robot action. The backend API environment alone
does not contain simulation dependencies; use GEMINI_PREFLIGHT_PYTHON and
GEMINI_SKILLS_ROOT when building the Site from another interpreter.

`tools/qualify_yam1_scene.py` runs a source-visible handwritten engineering
rollout in the separately qualified container. Its receipts/video record actual
simulator output, not a Hydrogen-generated task or physical success. The first
60-frame/6sim-second proof took87.774s in-container/89.681s executor wall on the
existing1CPU allocation, with no MuJoCo numerical warnings. A follow-up hides
nonphysical IK markers and preserves360pixel image height without stretching.

Remaining: connect this provider to production lifecycle/capture/replay; bind a
fresh actual scene and tested controller; qualify collision/contact behavior;
complete Cartesian and full native command-contract coverage; restore selected
Hydrogen access; then perform representative manipulation and normal-UI physical
acceptance with every required timing/live/history evidence item. Scope is
unchanged and unchecked checklist requirements remain open.

Final source-bound channel matrix (evidence/controller-channel): normal1.214s ready/1.613s total, cancel1.217s/2.757s, oversized1.259s/2.609s. Normal produced2packets/4waypoints; both negative cases produced0packets. All three named containers were confirmed removed. Exact runtime/host/client source hashes match this checkpoint. This measures offline channel behavior, not native physical Stop latency.

## Common MuJoCo backend and runtime qualification

`yam1_simulation.py` implements the same DeviceLayer/command compiler as the
host RPC bridge. It integrates actual MuJoCo state, preserves untouched fields
in full packets and rejects invalid inputs before changing state/time/cursor.
Native-default joint settling advances simulation time and retained frames.

Actual runtime exposed copied stock-Pro assumptions that were wrong for the
installed tool: Google DAMPING150 belongs only to actuator kv, and installed
i2rt normalized command/readback mappings are inverse linear. Double-applied
finger damping and the stock preload offset were removed; the finger command
is fraction times0.0475m per jaw. A no-load0.375 hold drifted0.06306555 before
repair and passes the numerical hold regression after repair. The simulation
now applies nominal robot-only CAD gravity compensation while preserving
world gravity for future objects. No native hardware gains or limits changed.

Image65f9521ae13c7d3cd087487d6cc3ade2860a79c2fc2797d313feb2f5f6029e84
passes ten isolation/runtime checks and a handwritten common-controller
rollout:43frames/4.3simseconds,34.652s in-container/37.528s executor wall, no
numerical warnings. Actual final grips were0.9972433 and0.9982549. Cold rootless
preparation first exceeded120s; after process/container termination was verified,
a warm offline retry passed. Existing isolation/resource limits were preserved.
The prior image/rollout and failing/passing regression remain retained under
`evidence/common-runtime`. These results do not certify physical force/contact
accuracy, object geometry, task success or the15s/30s onset requirements.

`station_inputs.py` uses the canonical read-only observation/calibration and
bounded JPEG transport, then constructs actual SDK Image parts. Source feedback
must retain the native freshness window. Trusted original input files and
hashes live outside generated-code workspaces; forged workspace copies cannot
replace public artifacts. The actual live probe stopped before images/model
on stale joints; source mesh peer blupe-jetson is offline. No session was made.

Required preflight now passes40tests plus gateway/inline-JS checks. Removing
station-input coverage makes it fail. The older channel matrix remains historical
evidence; its source hashes predate current scene/environment refinements and
must be requalified before claiming the updated physical path validated.
