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
YAM while live control remains Robo-house, plus scoped history, stale responses,+cross-station replay, mixed boxes and context counts. The new UI and Python
regressions both fail against the original code and pass with the repair.

## Scoped checks

- [x] Default root-page omission reproduced; global and YAM APIs contain RoboSkills.
- [x] Runtime UI regressions pass; all 348 shared JavaScript checks pass, and
  all 427 hosted-compatible shared JavaScript checks pass.
- [ ] Python/shared and hosting validation complete, source/pin published.
- [ ] Deployed root page finds/selects RoboSkills while live control stays Robo-house.
- [ ] Public model-filter results and retained replay verified after deployment.

Broader RoboSkills acceptance remains 12/15, with representative manipulation,
every-run timing and final qualification requirements open. This repairs history
discovery only and does not change prior owner exceptions or publish the excluded
historical recording. See the preserved
[integration checklist](../../../integrations/roboskills/site/docs/COMPLETION-CHECKLIST.md).
