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
