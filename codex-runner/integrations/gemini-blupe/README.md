# Gemini × BluPe

Separate Gemini-only BluPe surface, retaining the live-camera layout and adding
simulation/results. User-selected model: Gemini 4 Hydrogen. Site title: Gemini.

This implementation is in progress. The worker has persistent runs, runner
attribution, normal SDK skill/workspace configuration, cancellation and retained
simulation artifacts. It does not yet have a qualified physical YAM1 adapter.
Physical Run returns an explicit unavailable response without submitting motion.
The integration is not complete until docs/COMPLETION-CHECKLIST.md is verified.

The official Robotics plugin and companion MuJoCo Playground are fetched at
exact commits into the worker environment. Use Python3.12 and a dedicated
container/process workspace; the SDK shell is not a Python security sandbox.
The existing controller retains hardware ownership and its normal queue,
readiness, command validation, limits, Stop and parking.

## Development

Install backend/requirements.txt into an isolated environment. Set
GEMINI_API_KEY, GEMINI_SITE_TOKEN, GEMINI_SKILLS_ROOT and GEMINI_STATE_DIR in
the private worker environment. Run uvicorn backend.gemini_worker:app on a
loopback/private interface. Public website proxy configuration uses BACKEND_ORIGIN
and BACKEND_TOKEN through Sites environment variables, never browser code.

No model key, runner email, private operational state or worker token belongs in
source. Public demo evidence is published under the harness contract. Simulation runs retain actual controller/report/video with checksums;
agent self-report is not physical or task-success verification.

## Isolated YAM1 simulation

The hosted SDK enables only custom skill/API-reading, controller-writing and
simulation tools. Builtin commands and subagents are disabled. Generated Python
runs in a per-run rootless Podman4.9.3 container with no network or keys, a
read-only image, one job mount and CPU/memory/process limits. Readiness requires
a real isolation and simulation receipt bound to the immutable image ID.

The selected source now uses an adapted bimanual YAM1 scene and a common
controller API for MuJoCo and the canonical hardware provider. Camera geometry,
object/contact behavior and physical task acceptance remain unqualified.
The currently deployed API remains e075e8d3 using the earlier single-arm image;
this new API release is packaged pending restoration of existing SSH access.

Build backend/Containerfile, configure GEMINI_SIM_IMAGE to its sha256 image ID
and GEMINI_EXECUTOR_PROOF to the private qualification receipt. The API itself
needs only backend/requirements.txt; simulation dependencies remain in the image.

## Required release preflight

Run `python tools/preflight.py` using the isolated Python3.12 Google Playground
MuJoCo4 environment plus backend requirements before every release. Set
GEMINI_SKILLS_ROOT to the pinned plugin skills directory. The API-only backend
environment does not contain simulation dependencies.
The Site builder enforces this too; set GEMINI_PREFLIGHT_PYTHON to that environment
when building with a different Python. See docs/COMMAND-CONTRACT.md for the
partial command coverage and explicit remaining integration/physical gaps.

Google HTTP402/prepaid-credit exhaustion is persisted as model unavailability.
The API key was installed with explicit user approval. Current inference is
blocked by depleted Google credits; no model or spending fallback is selected.
After the owner restores billing, retain the original failure and perform a
bounded actual provider check before clearing that unavailable state.

## Bimanual adapter checkpoint

The offline installed-geometry/Google-IK adapter and isolated generated-controller
bridge are implemented and tested; see [YAM1 adapter evidence](docs/YAM1-ADAPTER.md).
The new API release is not enabled in the production worker yet. Physical Run, model-generated
YAM1 simulation, contact qualification and full checklist acceptance remain open.

## Common-controller engineering checkpoint — November18,2026

The same `run(env)` now reads measured state and emits canonical packets in
MuJoCo and the isolated host bridge. The worker captures fresh native station
feedback and three actual JPEG inputs before model generation, keeping those
inputs outside the generated-code workspace. Stale station feedback fails
before model inference. See [controller API](docs/YAM1-CONTROLLER-API.md).

The repaired image65f9521a passes ten actual isolation/runtime checks and a
handwritten43-frame/4.3sim-second rollout (37.528s executor wall). Source-bound
receipts and replay are in [evidence/common-runtime](evidence/common-runtime).
The first rollout and the failing gripper regression are retained. Required
preflight passes40tests plus gateway/JS; removing input coverage fails release.
These are offline engineering results, not a model-generated manipulation task.

Production Google credits remain depleted. YAM1's source peer is offline and
its public joints are stale. Physical Run stays unavailable. The complete
integration checklist remains1/17 checked.
