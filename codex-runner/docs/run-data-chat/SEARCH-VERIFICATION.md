# Fast full-library prompt lookup — verified November 1, 2026

User request: search the different run prompts across the whole library, and make it fast.
This is read-only public data discussion, separate from robot queue or harness identity.
No name/email, model inference, recording or robot command was needed for these checks.

- [x] Every full prompt and saved annotation in the selected scope is searched before
  choosing evidence. Text after the former 800/1200-character excerpts is included.
- [x] Default all-runs knowledge and separate library/robot/filter/replay context remain
  intact, including the concurrent independent library robot filter.
- [x] Simple lookups bypass the model, preserve validated replay navigation, resolve
  the user topic in pronoun follow-ups and accept the misspelling unpluged.
- [x] The camera incident questions find both matching prompts across all 1,426 records;
  a new task topic and a no-match case work too. Rapid follow-ups have no analysis cooldown.
- [x] Cache keys include full text; public source inputs refresh after at most five
  seconds and expose snapshot age. Failed refreshes are not marked fresh.
- [x] Actual public API timing, complete counts, match IDs, no-model provenance,
  affected checks, exact code CI and hosted ownership/integration checks are retained.

[Machine-readable evidence](evidence/full-search-verification.json) records seven live
requests. The six warm requests measured 425.8 ms median over HTTPS (309.94 ms server time),
with165–983 ms HTTP range. First uncached response was 1,718 ms. These are measured examples,
not a latency guarantee. There were zero model calls and zero hardware commands.

The first citation is [ep_07f4575dde7c49e8](https://playground.blupe.io/?robot_id=robot-ba8413962083809c&run=ep_07f4575dde7c49e8#past-runs):
“with the left hand, reach around and unplug the cable from the camera on the right hand”.
A prompt records the requested task, not proof of physical execution or causation;
saved automated annotations remain predictions. No recording was inspected by the search.

Shared source: [search PR261](https://github.com/andlyu/blupe-remote-bots/pull/261) and
[latency PR264](https://github.com/andlyu/blupe-remote-bots/pull/264), final merge cd4c9dc.
Hosted-compatible code e8d0e39 preserves scope pin 4d3067c; hosted pin merge b07a13a.
Exact final public source and compatible CI both passed (links in JSON).
The hosted runner could not start, so its status is an explicit CI exception:
its exact final snapshot instead passed 431 Python tests, 9 skips, 21 subtests (60.97 s),
45 JavaScript checks (0.086 s), and the required ownership check locally.
Affected source checks: 75 Python/API plus 4 subtests; compatible 73 plus 4 subtests.
The frontend JS is unchanged by the final cache optimization; 427 compatible JS checks passed.

Deployment used current-file hash guards, zero-fuzz narrow patches, backups and atomic
writes. A concurrent scope update was caught before any mutation and preserved. Fresh
idle checks for all four published robot views preceded each web-service restart;
robot gateways, subscription broker and physical controls were untouched.

All applicable search requirements above are verified. Physical-method integration,
GPU provisioning, queue identity and arm-motion timing are N/A to this read-only feature.
