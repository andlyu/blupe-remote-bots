# Control contract: required before physical runs and completion

This is a required engineering gate, including when an integration preserves an
older completion checklist. It adds no identity, robot or publication permission
and does not change the authorization contract, approval handling or hardware
safeguards. Installing these instructions alone is not passing evidence.

## 1. Test every advertised command through the real packet path

Inventory the commands the integration actually exposes: state/camera reads,
joint and Cartesian motion, gripper open/close/fraction, and any other advertised
primitive. Record arm support, coordinate frames, units, numeric ranges and
unsupported behavior. Do not advertise an untested primitive as working.

Before a physical run, exercise every applicable primitive offline through the
integration's actual command parser, trajectory generator, complete serializer
and the deployed version of the canonical client validator. A formula-only test
or a mock which accepts arbitrary packets is insufficient. Use a transport spy
or mock station: the tests must send no physical command. Confirm that locally
rejected input produces zero outbound actuator submissions.

For both arms where supported, cover:

- Legal lower/upper endpoints, ordinary interior values, and fractional measured
  starting states. For a normalized gripper include close=0, open=1, a partial
  target and a measured start such as 0.9992793312193716 closing to zero. Testing
  only a convenient start such as 0.5 is insufficient.
- The first, interior and final generated waypoints; finite values, correct
  units/frames, endpoint accuracy, contiguous command IDs, pacing/budgets and
  preservation of every uninstructed joint, arm and gripper.
- Values just inside and just outside legal bounds, negative/above-one gripper
  requests, NaN, infinity and malformed input. Invalid requested targets must
  remain rejected, including tiny out-of-range values.
- Fresh feedback/calibration requirements and the unchanged joint, workspace,
  predictive-contact, queue/lease and Stop checks applicable to the adapter.

Record the runnable command, exit status, test output, exact source revision,
dependency/validator version and coverage matrix. Wire the test command into a
required CI check or deployment preflight; a release must fail when it fails or
required coverage is missing. If a standalone integration has no CI, its release
procedure must execute the same gate and retain the result before deployment.

## 2. Produce valid numbers without weakening safety limits

Preserve an already-validated exact target at the final interpolation waypoint.
Do not recompute close=0 with subtract/multiply/divide if doing so introduces an
out-of-range residual. Check the generated and serialized packet, not just the
requested target. Other endpoint-safe interpolation is acceptable when tested
through the same complete packet path.

Do not widen joint/workspace/actuator bounds, disable finite checks or blindly
clamp an invalid requested target to make a test pass. If any numeric tolerance
is necessary, document its units, justified magnitude and precise application;
test that genuinely invalid input still fails. Prefer exact endpoint generation
for an exact endpoint command.

The motivating failure was a valid gripper-close request whose generated final
fraction became -1.1102230246251565e-16. The strict [0,1] validator correctly
rejected the packet; the defect was the adapter's interpolation. Gripper-value
validation and physical workspace/contact protection are distinct checks.

## 3. Validate locally and preserve the dispatch boundary

Validate a complete generated packet before handing it to the execution worker
or transport. Known local schema/range errors should become actionable tool
results while no motion has been submitted, rather than becoming an opaque
whole-run cancellation. Preserve the original error, field, waypoint and value.
Test this behavior through the actual runtime bridge/controller path.

Keep packet construction/local validation, transport send, gateway acceptance
and measured completion distinguishable in logs and UI. Label errors as local
input/generation rejection, planning/workspace/contact rejection, transport or
unknown execution outcome, or physical safety stop as the evidence supports.
An error mentioning a gripper fraction is not evidence of a physical boundary
crossing. An enqueue/requested event is not evidence of dispatch or motion.

A new planning step may revise a proven-not-dispatched local rejection using
fresh required state/images and the existing command limits. Do not silently
replay the rejected packet. Timeouts, unknown dispatch/execution outcomes and
explicit tool/approval denials retain their existing stop/non-replay handling;
this rule grants no retry or approval bypass for them.

## 4. Turn every failure into a regression

Retain a sanitized failing request/packet and the relevant measured starting
state. Reproduce the exact failure offline; show the regression fails on the old
code and passes after the repair through the same real validator. Check that
unrelated command fields and all safety protections remain correct. Run the
appropriate broader suite. A hand calculation or a claim that the value is
"too small to matter" is not verification.

## 5. Match acceptance to the task and invalidate stale passes

Keep software/command-contract checks, model/memory behavior, physical execution
and physical task success separate. State the tested task/capability and source
revision with each result. A joint wiggle can verify joint motion; it cannot
establish working pick-and-place or gripper control.

For advertised manipulation, the final normal-UI scenario must exercise the
relevant sequence: approach, grasp/close, lift, transfer, release/open and
withdrawal, with fresh state/visual evidence of the requested object outcome.
Record explicit exclusions for capabilities not advertised; do not claim broad
task success from a narrower test. A completed tool call, agent self-report or
retained video alone does not prove the object reached its requested state.

A later relevant failure or changed command-generation/validation code reopens
the affected requirements until matching regression and deployment evidence is
available. Keep earlier results as history. The current passed/total status and
completion claim must reflect those reopened requirements; a static badge based
on an earlier smoke test must not continue to imply current full acceptance.

## Evidence to retain

- Deployed source and validator/dependency revision; advertised primitive matrix.
- Required CI/preflight command and result; endpoint/interior/invalid-input and
  zero-dispatch failure tests, including preservation of uninstructed targets.
- Sanitized original failing packet, dispatch classification, red-to-green
  regression and safety-preservation evidence for each repair.
- Representative physical task/run, observed outcome, ordinary harness timing,
  live/replay links, tested scope and exclusions; remaining unchecked items.

These requirements demand executable checks in each integration. The shared
installer distributes and verifies the instructions; it does not itself run an
integration's tests, inspect arbitrary adapters or certify a robot task.
