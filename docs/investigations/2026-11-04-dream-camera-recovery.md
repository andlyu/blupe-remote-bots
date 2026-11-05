# Dream camera recovery and failure diagnosis

User request: “Look, we need to figure out and fix it”, following Mike Dressler's failed black-pen handoff, episode `ep_378021a307c544df`, Robo-house YAM (`robot-ba8413962083809c`). The adopted AGENTS.md selects the shared [harness authorization contract](../../codex-runner/integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness) for this playground fix and its bounded verification/public delivery.

The episode failed in `predicting` with `RuntimeError` at 22:47:51.701 Pacific, 75.4966 seconds after recording started. Its last native motion packet was completed. Newly recovered SDK traces show the last prediction itself completed at 22:47:48.312, followed by an SDK history reset at 22:47:51.238. Native observer traces retain camera capture errors before termination, including repeated HTTP errors near the end. The original exception message was discarded, so these historical records do not uniquely prove which input check raised it.

A real localhost HTTP camera reproducer establishes a matching software defect: exhausting one camera retry batch turns even a retryable HTTP 503 into a permanent Dream observation failure. A frame available on the next attempt cannot recover, and `_wait_for_ticks` raises `RuntimeError`. The reproducer failed before the repair and passes afterward. This verifies the repair's failure mechanism independently of the unavailable historical exception.

The repair preserves camera retryability into the collector's existing bounded recovery window. It clears old history, requires fresh complete camera/state inputs before the next prediction, and keeps permission denials, identity changes and invalid measurements terminal. Persistent outages still terminate without a model request. Native movement limits, queue/lease ownership and Stop behavior are unchanged; no timed-out movement is retried.

The native executor now retains allowlisted camera/feedback field, HTTP status and cause class, plus code locations for otherwise unclassified exceptions. It retains no raw exception messages, stack locals, images or private provider payloads. Terminal observation diagnostics are published before waking the executor, preventing a shutdown race from losing the cause. The hosted runner reports input recovery while prediction is paused and displays the specific failed input instead of the generic hardware-safety banner.

Verification:

- [x] Failing-before-fix HTTP reproducer: two failures and one pass; 2.22 seconds.
- [x] Final shared Python suite: 1,561 passed, 100 skipped, 330 subtests passed; 149.67 seconds. Missing UMAP packages from the first run were installed only in a task-specific temporary test directory.
- [x] Shared JavaScript suite: 358 passed; 0.703 seconds.
- [x] Exact Robo-house deployed baseline plus the minimal repair: 151 focused tests passed; 19.68 seconds. Existing station-specific model routing and calibration code are preserved.
- [x] Manual diff review and whitespace check; input recovery, permanent denial, persistent failure, cancellation, freshness and private-payload redaction covered.
- [ ] Publish/merge reviewed shared source and activate the minimal overlays during an idle, empty-queue maintenance window.
- [ ] Verify a normal 120-second Dream-1 beta black-pen handoff run, retain native/journal evidence and replay. Runner `andrew` and email were explicitly confirmed in this chat; private contact details remain outside public source/demo evidence.

Deployment and physical verification are pending at this source snapshot. Offline checks establish recovery behavior, not successful pen manipulation or a reproduced physical camera outage.
