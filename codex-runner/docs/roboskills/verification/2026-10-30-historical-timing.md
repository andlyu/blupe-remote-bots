# RoboSkills historical timing audit

Audited 2026-10-31T06:25:04.339632+00:00. Scope: all six retained physical website runs. No new arm run was needed.

The current Site version13 passed a full anonymous UI physical test. This audit preserves the older failed or incomplete timing evidence; later passing results do not rewrite those runs.

| Run | Recorded click bracket (UTC) | Observed queued→first grant receipts (s) | Nonqueue time before the first possible method motion | Time after Home/readiness before the first possible method motion | Outcome |
| --- | --- | --- | --- | --- | --- |
| `453a9a037e874840ad4382597c25e8c1` | 03:11:49.691Z–03:11:50.130Z | 10.084 | ≥30.720s (lower bound) | ≥29.380s (lower bound) | MISSED: both current timing targets |
| `249450342a5e4286b9d406d3e8738d34` | 03:37:20.120Z–03:37:20.461Z | 10.309 | ≥30.551s (lower bound) | ≥28.160s (lower bound) | MISSED: both current timing targets |
| `13e819ec7b494429ab91a8a09f41e645` | 04:10:17.632Z–04:10:17.953Z | 11.244 | ≥14.966s (lower bound) | ≥13.689s (lower bound) | UNVERIFIED: historical Home/clock evidence incomplete |
| `62623309ad3c4c47a88aa91ef209668a` | 04:18:15.638Z–04:18:16.013Z | 10.196 | ≥10.590s (lower bound) | ≥10.227s (lower bound) | UNVERIFIED: historical Home/clock evidence incomplete |
| `2ea288ea830e471a86eb6d1d98971c50` | 04:21:30.927Z–04:21:31.276Z | 95.846 | ≥10.976s (lower bound) | ≥9.268s (lower bound) | Run pass under owner queue rule; historical post-Home not fully qualified |
| `b1d79ff0fe8944e8ab47342bdcffbad2` | 06:02:27.070Z | 26.277 | ≤13.864s (visual upper bound) | ≤13.133s (visual upper bound) | PASS: current release; both targets, with bounded clocks |

## What the bounds prove

A method-driven move cannot happen before its first command packet is prepared. For a historical failure, the audit conservatively allows the queue to consume the entire interval from queue-request start to receipt of the first matching grant. This is more time than the true queue can consume. Even deducting that maximum, runs453a9a and249450 had already exceeded30seconds when their first method packet was merely prepared. Their post-Home packet preparation already exceeded15seconds too, starting from the later received `running/first_observation` readiness event. These two failures use differences on the same local clock, without requiring a retrospective clock-offset assumption.

These are failure lower bounds, not exact visual onset times or permitted queue deductions for a passing run. The audit never applies this maximum queue deduction to establish a pass. Home/startup preparation and unrelated users’ motion are excluded from method onset.

The older13e819/626233 recordings show actual motion, but original Home sample and clock-bound receipts are incomplete. Their original Run clicks were recovered from the retained same-chat tool receipts:04:10:17.632Z and04:18:15.638Z. Missing original timing evidence remains unverified.

Run2ea288 retains its previously accepted owner-specific queue-excluded Run upper bound14.442s. Its older post-Home evidence is not upgraded by later clock measurements.

Runb1d79f on version13 has separate matched Home, visual onset, queue and clock receipts; both current upper bounds pass. See2026-10-30-no-signin-final.json and2026-10-30-no-signin-lifecycle.json.

## Remaining decisions

- The pre-version-13 runs include proven timing misses and incomplete original measurements; their release acceptance uses the explicit owner exception below. No GPU or research exception was invented. The owner explicitly answered “Accept historical exceptions” for the five pre-version-13 runs. Their failures/missing measurements remain recorded; current v13 passed and future timing limits remain unchanged.
- The original failed recording453a9a stays local under the prior automatic-review denial of that specific public upload. This audit publishes timing metadata only; no footage, frames or transformed derivative of that denied recording is included. The owner subsequently excluded this old failed clip from the release-required archive; the exact instruction is recorded below. No upload is needed for completion.

Current release: https://blupe-bimanual-skills.andlyu.chatgpt.site/#physical-yam
Current source: https://github.com/andlyu/blupe-remote-bots/pull/177

Owner acceptance recorded: “Accept historical exceptions”, applying only to the five listed pre-version-13 runs. Run-click failure lower bounds use the post-action tool-response timestamp, not the earlier pre-click marker. The earlier table draft has been corrected accordingly; the two proven misses remain misses.

## Final owner scope decision

The user stated: “so why is this an issue? This just simply doesn't matter. All that we care about is that the method is reflected and that the 15 reqs pass”. In context this excludes publication of the original failed clip from release completion. The existing local recording and prior denial are retained. Current method fidelity and the15 requirements remain required; this archive exception does not weaken them or future timing limits.
