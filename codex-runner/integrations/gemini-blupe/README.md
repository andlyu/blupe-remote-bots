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

No model key, runner email, private state, recording or worker token belongs in
source. Simulation runs retain actual controller/report/video with checksums;
agent self-report is not physical or task-success verification.

## Isolated reference simulation

The hosted SDK enables only custom reference-reading, controller-writing and
simulation tools. Builtin commands and subagents are disabled. Generated Python
runs in a per-run rootless Podman4.9.3 container with no network or keys, a
read-only image, one job mount and CPU/memory/process limits. Readiness requires
a real isolation and simulation receipt bound to the immutable image ID.

The current simulation scene is Google’s official single-arm reference. It is
not yet a calibrated bimanual YAM1 twin. The physical adapter remains pending.

Build backend/Containerfile, configure GEMINI_SIM_IMAGE to its sha256 image ID
and GEMINI_EXECUTOR_PROOF to the private qualification receipt. The API itself
needs only backend/requirements.txt; simulation dependencies remain in the image.

## Required release preflight

Run `python tools/preflight.py` using the backend environment before every release.
The Site builder enforces this too; set GEMINI_PREFLIGHT_PYTHON to that environment
when building with a different Python. See docs/COMMAND-CONTRACT.md for the
partial command coverage and explicit remaining integration/physical gaps.

Google HTTP402/prepaid-credit exhaustion is persisted as model unavailability.
The API key was installed with explicit user approval. Current inference is
blocked by depleted Google credits; no model or spending fallback is selected.
After the owner restores billing, retain the original failure and perform a
bounded actual provider check before clearing that unavailable state.
