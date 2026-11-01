# RoboSkills discovery in the default model filter

The user supplied a November 1 screenshot showing a search for `RoboSkills`
with “No matching models”, after requesting its model label in BluPe history.
This follow-up invokes the adopted harness playground-fix workflow. The
authorization-by-use contract covers this public website/source repair at
https://playground.blupe.io and https://github.com/andlyu/blupe-remote-bots.
No physical run, identity submission, policy inference, new recording or media
upload is needed. Existing visibility exceptions remain unchanged.

## Cause and repair

Reproduced on the ordinary root URL: live control defaults to Robo-house YAM
(`robot-ba8413962083809c`). The history UI unconditionally attached that robot to
the catalog query, so its model dropdown omitted RoboSkills even though all 35
confirmed receipts were correctly labeled on `yam-1`. The previous browser proof
explicitly selected YAM and did not cover the default page.

The public **All runs** library now has a separate **Robots** filter, initially
**All robots**. Its catalog and model options cover all public stations; choosing
a history robot narrows both without changing live control. Station-local
playgrounds retain their local scope. Search, pagination and Cloud share the same
explicit library scope. Preview/replay requests use each recording's robot.
Mixed-station box selections retain all selected runs. Data-chat context receives
the actual library scope while its existing session/CSRF/provider boundaries stay
intact. No model selection or controller code changes.

The safety fact is that these paths only read already-public history and retain
the live-control robot separately. Runtime regressions exercise RoboSkills on
YAM while live control remains Robo-house, plus scoped history, stale responses,
cross-station replay, mixed boxes and context counts. The new UI and Python
regressions both fail against the original code and pass with the repair.

## Scoped checks

- [x] Default root-page omission reproduced; global and YAM APIs contain RoboSkills.
- [x] Runtime UI regressions pass; all 348 shared JavaScript checks pass, and
  all 427 hosted-compatible shared JavaScript checks pass.
- [x] Python/shared and hosting validation complete, source/pin published.
- [x] Deployed root page finds/selects RoboSkills while live control stays Robo-house.
- [x] Public model-filter results and retained replay verified after deployment.

## Delivery evidence

[Shared PR260](https://github.com/andlyu/blupe-remote-bots/pull/260) merged as
`95ddfe88fff24a74fc17e198a9076ec1459898ee`, with all GitHub checks passing
(run `41349364561`). The full local shared suite passed 1,440 tests and 181
subtests with 100 skips, in 100.656 seconds command wall time. It used an existing
complete dependency environment and allowed temporary localhost fixture sockets;
earlier runs in a restricted/incomplete environment were not passing evidence.
The complete hosted suite passed 401 tests and 21 subtests, with one skip, in
62.858 seconds command wall time.

The published compatible backport `4d3067c2aef38053a7e7f2c5abce6fa0b83067ec`
preserves the hosting base's ASPIRE modules. Its one-line dependency update merged
in [hosting PR199](https://github.com/andlyu/blupe-evals/pull/199), merge
`6c5b7a36f3a183878e8b988f363d8af16bab08bf`. GitHub's hosted job did not start due to
account billing/spending limits (run `41349772869`); the equivalent local suite
passed. No protection or workflow setting was bypassed or changed.

Deployment at 2026-11-01T21:05:12Z preserved the actual Caddy-served meeting UI
overlay. Every changed block matched exactly once in fresh copies; syntax checks
and 19 relevant runtime regressions passed against those exact candidate bytes
(3.058 seconds command wall). A separate existing markup-only assertion expects
the canonical literal `<ol id="pastRunsList">`, while the retained overlay adds
attributes; it is not evidence of a runtime failure. The complete canonical and
compatible JavaScript suites passed as recorded above. Neither old staging patch
check that found the wrong asset location changed production.

All four robot queues were empty before the website-only restart (3.412 seconds).
Both Spotter service PIDs were unchanged. The existing RoboSkills metadata timer,
native footage/outcomes and exclusions were retained; robot commands and new
recordings were zero.

Public HTTP verification at 21:06Z found 35 RoboSkills runs in both Table and
Cloud and 22 Spotter runs. Root HTML and JavaScript hashes matched deployment.
The normal browser root navigation had no robot-selection URL parameter: live
control remained `robot-ba8413962083809c`, history selected All robots, typing
`RoboSkills` returned exactly that visible checkbox and hid the empty state.
Selecting it showed “35 runs · newest first.” with the actual global library
scope. The known retained `ep_a41fd6cf5ebd402e` replay opened from that scope,
displayed `RoboSkills`, played to 0.400652 seconds and sought to 0.2 seconds of
its 0.8-second quick preview, readyState 4 with no video error. Live control was
still Robo-house. This is existing-media verification, not a physical task test.

Deployed SHA-256:

- HTML: `7dec168a8ae51a35231479f82aa52fc239e0cdc18774ec3e91263b5b43cee751`
- History UI: `de1dbecf0a3a80bc222b8d78cf0071873621819e653f5b05c89e9f79eb025766`
- Replay UI: `f2d909d543f23b5b75b92d290bb8a26d9411a43486e1178d5d995e925215c843`
- Chat scope module: `38ee68dddb16397c515d388368f678748c40850922849bbc029bbdf1ce9eb471`

Broader RoboSkills acceptance remains 12/15, with representative manipulation,
every-run timing and final qualification requirements open. This repairs history
discovery only and does not change prior owner exceptions or publish the excluded
historical recording. See the preserved
[integration checklist](../../../integrations/roboskills/site/docs/COMPLETION-CHECKLIST.md).
