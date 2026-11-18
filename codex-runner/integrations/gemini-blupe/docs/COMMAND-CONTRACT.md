# Gemini YAM command path — partial offline qualification

backend/yam_commands.py compiles registered left/right DeviceLayer keys
`<arm>/follower/goal_position/joint1..joint6` (radians) and `gripper` ([0,1])
with duration_s into10Hz canonical degree-valued packets. It owns no robot,
lease, Home or transport. Unknown/malformed/non-finite/bool requests are rejected.
Native safety snapshot9a305c10a44e1093ebd21d138e992443263edb8dc5c06c3004c62371f2d3c69f
supplies unchanged joint/velocity/adjacent-step bounds. No Cartesian primitive
or physical bridge is advertised as qualified by this compiler.

Required release command: run `python tools/preflight.py` with backend dependencies
installed and Node available. tools/build_site.py executes this gate before it
writes/packs output. Missing named command/readiness cases fail the release.
The gate performs no model calls or network/robot submissions.

Tests cover both arms and all12joints: lower/upper endpoints, immediate interior
and exterior floats, fractional measured starts, first/interior/final waypoints,
contiguous IDs, preservation of uninstructed joints/arm/grippers and native
speed/packet/session budgets. Grippers include0,1,partial targets and the
0.9992793312193716→0 case. Invalid targets, NaN/infinity, booleans, malformed or
duplicate fields and exhausted budgets produce zero transport calls. The actual
HttpSessionAPI generator, validator and complete JSON/Request serializer run
against a transport spy, not an accepting substitute validator.

The first strict wire-range sweep failed at3endpoints: left/right joint1 target
-2.61799rad decoded as-2.6179900000000003rad, and left joint5 upper target
1.5418379241286437rad decoded as1.541837924128644rad. wire_degrees first validates
the requested radian target, then moves only an outward-rounded encoded degree
value one representable float inward. The strict native bounds never change;
invalid requested targets one float outside still fail. The final encoded
endpoint is retained exactly; decoded error is at most one radian ULP in tests.
There is no added range tolerance. Exact gripper endpoints are assigned directly.

Current15-test receipt: ../evidence/runtime/offline-preflight.json. This verifies
the compiler/client boundary, not native predictive-contact behavior, a full
RunnerController/Google controller composition, Cartesian mapping, matched
bimanual dynamics, physical onset or manipulation/replay success. These required
integration checks remain open; physical Run stays unavailable.

## Bimanual bridge continuation

The required release preflight now also exercises installed two-arm/finger FK,
provisional pinhole calibration, Google generic IK/residual validation and the
container RPC facade. Real RunnerController mock-station tests pass through the
actual canonical HTTP serializer, including local no-dispatch rejection/new-request
revision, exact gripper endpoints, Stop discarding late packets, request cursors
and matching settled completion. A real network-disabled container protocol proof
is retained separately. These remain offline software proofs: native contact
behavior, fresh physical calibration/state binding, Cartesian endpoint-to-dispatch
coverage, manipulation, onset timing and live/history acceptance are not passed.
See [YAM1 adapter](YAM1-ADAPTER.md). Physical Run remains unavailable.
