# Replay handoff identity and continuation

The native local-pose cancellation Event survives after its plan ends, including
across a later successful Replay. A flag belonging to the same inactive,
unreserved plan that was already cancelled before Replay does not invalidate
that new Replay's successful completion.

Admission still requires the matching primary request, complete acknowledged
waypoints, finish in Hold, healthy enabled controller, idle queue/API and no
pose owner. The primary's command source must remain `operator/replay`, phase
`replay_held`, and event `Replay complete; arms holding`. A new cancellation,
changed pose identity, current Stop/Hold, interrupted Replay, missing baseline
or another owner blocks admission. The old flag is never cleared by this code.
The baseline belongs to this request and passes through the existing shared I/O
connection to cube initialization.

Controller state is reread after pose status at handoff and initialization.
The native reserve operation clears its old Event but preserves command source
and event. A post-reserve check therefore rejects a Stop immediately before
reserve; a Stop after reserve revokes its owner token and the existing native
preview/execute rejects further commands. These checks add four read-only status
requests per combined handoff, not per waypoint. Their network latency has not
been measured separately; no native driver, motor, force, travel or gain changes
are required.

`--continue-after-replay RECEIPT_DIRECTORY` reuses `before.json`,
`replay-result.json` and `selected-replay.json` from a confirmed replay. It
requires the same recipe and request ID, retains input hashes, sends no Replay
start, and then checks current native completion identity before the existing
Home/scene/cube lifecycle. An omitted request ID uses the recorded replay ID.
Any Stop/Hold, another replay, or a dispatched Home/cube operation changes the
identity and prevents treating the old replay as an untouched continuation.
No uncertain accepted motion is retried. This is an explicit invocation, never
an automatic retry of a terminal run.

Software tests and retained-receipt checks do not certify a physical grasp or
finished reset. Continuation must remain within the operator's authorization;
preparing or installing this option does not itself request robot motion.
