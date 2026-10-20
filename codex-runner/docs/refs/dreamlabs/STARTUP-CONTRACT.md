# Pinned Dream SDK startup and observation contract

Verified against official dreamlabs-client1.0.0 and dreamlabs1.0.0 wheel sources used by this integration. This is a source-derived reference; it does not measure a production run.

- `dream/facade.py:DreamClient.__init__` reads the configured credential and binds endpoints; its contract says it sends no request or model session.
- `DreamClient.policy` opens a policy and creates a new observation window. `dream/client_ik.py:ClientIK.__init__` initializes the local solver. For EEF trajectory mode it warms the tick solve synchronously and starts trajectory compilation on a background thread; forward-kinematics initialization is also local. A duration around this whole policy call includes its setup and cannot automatically be called remote model inference.
- `set_observation` retains the newest measured state and a timestamped camera window. The SDK requires monotonic observation timestamps within an episode.
- `get_action` sends the latest state/window and creates or continues a stateful model session. Its EEF conversion/IK uses measured joint state and the commanded chunk anchor. A pre-Home prediction cannot be treated as a fresh post-Home prediction just by changing a flag or timestamp.
- The shared Astra/Codex HomeScene protocol uses actual saved Home observations and strict scene/lease/configuration/freshness checks plus bind/discard hooks. Dream does not implement that protocol. SDK setup may overlap native Home after lease grant; live Dream prediction remains after confirmed Home and fresh state/images.

Source SHA-256 values (wheel contents, not runtime timing evidence):
- `facade.py`: `24d3d83e21aaca76d48e20762864a249f4ca948560eb741a3211a51ad7f31104`
- `client_ik.py`: `6294e874f38d75526756acf42bc1592765367bf1fe2740e610c417297b845057`


## Resident solver and episode reuse

SDK1.0.0 `DreamClient.reset_episode()` delegates to `PolicyClient.reset_episode()` before clearing its `_window`. The documented contract ends the remote session and chunk blending without constructing another policy or IK solver. `PolicyClient` refuses a concurrent reset during get_action; therefore the resident manager drains its single in-flight reply before resetting and handing ownership to another visitor. It never resets concurrently with inference. The SDK window's clear operation empties the observation, frame rings, recent timestamps and collection schedule. `_record=False` continues to disable background recording.

Two prepared policies in one process retain their respective checkpoint metadata/embodiment checks and static IK configuration. Only the documented episode-reset operation crosses visitor boundaries. Checkpoint configuration is not rewritten and no native motion, feedback or Home logic changes. The SDK's pinned `_policy._ik.traj_ready` event is read during initial preparation to ensure background trajectory compilation has completed; an absent/incompatible event fails preparation instead of reporting ready.

Each wire command is handled in its own function scope; reset/release replaces outer command references. Before lending again, every prepared client has been reset successfully, the shared input timestamp is cleared, and no previous request result can be read as a new visitor's response. A failed cleanup or broken transport destroys the process. Credential file changes also invalidate prepared readiness.


## Both trajectory kernel structures

SDK1.0.0 `dream_ik/solver.py:ChunkIK.solve_traj` supplies Python `None` or the
arm-base array to the JAX-jitted `_solve_traj` kernel. Its synthetic startup
warmup exercises only the branch selected by those warmup targets. The two
argument structures compile separately; `traj_ready` alone does not establish
that both are prepared. Exact-SDK synthetic probes confirmed compilation on a
later switch to the arm-coupled branch.

After `traj_ready`, `remote_yam.dream_ik_preparation` captures the pinned SDK's
kernel arguments from a synthetic 48-row rest-pose solve, restores the original
function binding, and executes both base-argument forms. Materializing each
result waits for compilation and execution. Both checkpoints complete this
preparation before `fully_ready` is returned; preparation errors fail readiness.
No model request or robot observation is used, all synthetic results are
discarded, and solver weights, joint limits, speed caps and runtime branch
selection stay as configured by the SDK. This depends on SDK1.0.0's private
kernel signature and must be revalidated on SDK upgrades.

The October20 incident trace establishes an IK timeout following a successful
HTTP response, while steering was still queued. It does not retain the target
poses needed to identify that historical solve's branch. Preparing both forms
closes a verified coverage gap; it does not prove the exact low-level cause of
that particular timeout or establish successful physical steering.
