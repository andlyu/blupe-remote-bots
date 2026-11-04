# Task-cloud startup loading

User invocation (2026-11-04): “there was also feedback that teh poitn clodu was slow to load”. The user-adopted AGENTS.md routes this playground fix through the [authorization-by-use contract](../integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness), which authorizes “committing and pushing its source, and deploying or updating its publicly hosted website.” Public scope: https://playground.blupe.io and https://github.com/andlyu/blupe-remote-bots. No queue entry, identity submission, physical run, new recording, assessment or label write is required. This is a library-loading fix, not a research integration; physical/model acceptance items do not apply.

The library previously waited for every imported label's explanation, confidence, rubric, limitations and timestamped video evidence before drawing its correctly colored cloud. Production compression already works. On the measured 1,261-label snapshot, the full response was 1,324,807 JSON bytes / 258,202 compressed wire bytes (one HTTP sample: 0.765s). The 1,509-run catalog was 1,569,651 JSON bytes / 191,119 compressed wire bytes (one compressed sample: 1.186s). These are individual HTTP samples, not browser percentiles or an end-to-end startup guarantee.

`GET /api/run-labels?summary=1` now returns the same episode/station IDs, automatic outcome/model and human-review outcome. This preserves all colors, provenance, eligibility rules and neighborhood counts while omitting replay-only evidence. The same live fixture reduces to 222,768 JSON bytes / 19,698 locally gzipped bytes (about 92% less compressed label data). The cloud still loads labels in parallel with the catalog and waits for the correct labels before rendering.

Opening a replay fetches `GET /api/run-labels?episode_id=…&robot_id=…` for that run's complete evidence. Concurrent requests and revisits share the result. Inline progress appears immediately; failures explain how to retry without discarding the cloud's labels. Late responses cannot replace the currently selected run. The unfiltered export remains unchanged, and older backends that ignore the query still work. Local public-queue launches forward these query strings through their existing read-only proxy.

## Verification

- [x] Read current shared source, ownership instructions and harness contract; preserve existing checkout changes by using an isolated checkout.
- [x] Reproduce the startup dependency and measure public transfer sizes; confirm compression already exists.
- [x] Regression tests fail on original frontend, then pass with compact startup/scoped evidence/retry behavior.
- [x] API tests preserve each automatic/human outcome, retain the full export, enforce station scoping and reject ambiguous duplicate filters; no assessment or session writes.
- [x] Existing correct-label loading barrier, cloud interactions and replay-preview tests pass.
- [ ] Full required regression checks pass on the final revision.
- [ ] Source published/reviewed and deployed asset/API behavior independently verified.
- [ ] Public cloud and selected replay evidence verified in the browser.

Current evidence: focused UI67/67; initial full UI357/357; focused Python7 passed. Full Python suite and public delivery are pending at this snapshot. Command receipts and live fixtures are task-specific files in /private/tmp; final outcomes must replace this pending status.
