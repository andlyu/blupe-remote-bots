# Dream camera recovery and failure diagnosis

User request: “Look, we need to figure out and fix it”, following Mike Dressler's failed black-pen handoff, episode `ep_378021a307c544df`, Robo-house YAM (`robot-ba8413962083809c`). The adopted AGENTS.md selects the shared [harness authorization contract](../../codex-runner/integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness) for this playground fix and its bounded verification/public delivery.

The episode failed in `predicting` with `RuntimeError` at 22:47:51.701 Pacific, 75.4966 seconds after recording started. Its last native motion packet was completed. Newly recovered SDK traces show the last prediction itself completed at 22:47:48.312, followed by an SDK history reset at 22:47:51.238. Native observer traces retain camera capture errors before termination, including repeated HTTP errors near the end. The original exception message was discarded, so these historical records do not uniquely prove which input check raised it.

A real localhost HTTP camera reproducer establishes a matching software defect: exhausting one camera retry batch turns even a retryable HTTP 503 into a permanent Dream observation failure. A frame available on the next attempt cannot recover, and `_wait_for_ticks` raises `RuntimeError`. The reproducer failed before the repair and passes afterward. This verifies the repair's failure mechanism independently of the unavailable historical exception.

The repair preserves camera retryability into the collector's existing bounded recovery window. It clears old history, requires fresh complete camera/state inputs before the next prediction, and keeps permission denials, identity changes and invalid measurements terminal. Persistent outages still terminate without a model request. Native movement limits, queue/lease ownership and Stop behavior are unchanged; no timed-out movement is retried.

The native executor now retains allowlisted camera/feedback field, HTTP status and cause class, plus code locations for otherwise unclassified exceptions. It retains no raw exception messages, stack locals, images or private provider payloads. Terminal observation diagnostics are published before waking the executor, preventing a shutdown race from losing the cause. The hosted runner reports input recovery while prediction is paused and displays the specific failed input instead of the generic hardware-safety banner.

Verification:

- [x] Failing-before-fix HTTP reproducer: two failures and one pass; 2.22 seconds.
- [x] Final shared Python suite: 1,568 passed, 100 skipped, 330 subtests passed; 143.92 seconds. Missing UMAP packages from the first run were installed only in a task-specific temporary test directory.
- [x] Shared JavaScript suite: 358 passed; 0.703 seconds.
- [x] Exact Robo-house deployed baseline plus the minimal repair: 158 focused tests passed; 19.54 seconds. Existing station-specific model routing and calibration code are preserved.
- [x] Manual diff review and whitespace check; input recovery, permanent denial, persistent failure, cancellation, freshness and private-payload redaction covered.
- [x] Published and merged [PR #288](https://github.com/andlyu/blupe-remote-bots/pull/288) and [PR #289](https://github.com/andlyu/blupe-remote-bots/pull/289), with canonical CI passing. Native numeric fix deployed at `84193832ea52ee9d9de314cfd375eb9053a895db`; hosted progress/error fix remains active. Source/station hashes and calibration identity were verified. Activation used idle, empty-queue maintenance windows and normal guarded Launch/Park.
- [x] Verified a normal 120-second Dream-1 beta black-pen task run, retaining native and hosted evidence: [ep_3679ea4565834b47](https://playground.blupe.io/?robot_id=robot-ba8413962083809c&run=ep_3679ea4565834b47). It ran 120.095 hosted seconds, completed 29 packets/696 counted waypoints, reached the selected runtime limit with no safety/controller abort, and parked with torque off verified. Runner `andrew` and email were explicitly confirmed; private contact details remain outside public source/demo evidence.
- [ ] Public video playback verification: the public run entry exists, but video is still processing at the handoff. Native recording finalized with 1,201 rows and zero capture errors. No successful pen handoff is claimed.

Deployment and the bounded physical runtime verification are complete. Public video playback remains unverified while encoding is pending. This verifies the runtime repair, not successful pen manipulation or a deliberately reproduced physical camera outage.


## Native numeric failure found by physical verification

The first post-deployment verification, [ep_801c3fb4167340de](https://playground.blupe.io/?robot_id=robot-ba8413962083809c&run=ep_801c3fb4167340de), stopped after 45.16 hosted seconds. Its last packet had completed, all 24 progress receipts and a final observation were present, and the retained reason was `missing_final_joints`. Recording capture errors were zero. Both arms parked normally with verified torque-off; no movement was retried.

The deployed native workspace-repair implementation builds corrected targets with `tuple(np.rad2deg(joints[part]))`, then retains those NumPy float64 values in its accepted receipt. Dream consumes this receipt directly before JSON serialization. Its exact-type numeric check rejects the valid values even though the equivalent JSON receipt passes. The measured-input validator has the same mismatch. This is a deterministic type-contract defect, rather than evidence of missing physical joint feedback.

An offline regression constructs the exact native receipt: the completion test and measured-input equivalence test fail before the fix, while malformed-value rejection tests pass. The repair uses the native API's `isinstance` numeric contract with explicit boolean/finite checks and normalizes measured grippers to Python float. The new tests and existing focused regressions pass (104 total). Final full Python checks pass with 1,568 tests, 100 skips and 330 subtests; exact-deployed-baseline checks pass 158 tests. A staged probe using the production interpreter also accepted the native receipt and rejected five invalid-value cases without any model call or dispatch. Canonical CI passed before activation. This follow-up does not change native guardrails or replay any motion.


## Final physical verification, November 5 Pacific

The post-numeric-fix run began at 00:05:15.898 Pacific and reached its selected limit at 00:07:15.993. Request-to-run-start delay was 10.813 seconds, including queue/admission/Home setup; this is not a pure queue-wait measurement. Native recording outcome is `session_timeout`, executor failure is null, hosted `safety_error` is null, and public history reports “Run reached time limit” with no errors. The executor's 29 packets and 696 completed-waypoint counters agree. Both arms then parked with verified torque-off and automatic admission restored to its original enabled setting. The calibration identifier remains `93c4db966dca49dbb831a2215f4dfc5fb83bf82eabfe99b3035a027aa7fc9275`.

Public aggregate execution metrics on this controller route still show zero, so they are not used as proof of no motion; retained native executor counters provide that evidence. The public replay entry is available while its video is processing. Native/hosted evidence and installed hashes were cross-checked offline. No claims are made about manipulation success or replay playback. The original Mike exception text remains unavailable; the camera-recovery defect and native numeric defect were independently reproduced, and the latter was observed during the first physical verification.

Status: runtime repair deployed and verified; public video playback is the remaining evidence limitation.
