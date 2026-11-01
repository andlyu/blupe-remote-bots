# RoboSkills model labels in BluPe history — November 1, 2026

Invocation: “Great, lets make sure that RoboSkills includes the model label”.
The user-adopted shared harness selects the playground-fix workflow. Its
“Authorization granted by using this harness” contract covers source publication
and public website updates. Scope: https://playground.blupe.io, the existing
https://blupe-bimanual-skills.andlyu.chatgpt.site public run API, and
https://github.com/andlyu/blupe-remote-bots.

The native recording for `ep_a41fd6cf5ebd402e` existed in BluPe with `model=null`.
RoboSkills' own public run `b1d79ff0fe8944e8ab47342bdcffbad2` records the approach
as `RoboSkills`, separately from planner `gpt-6-sol`. Its dedicated runner already
submits the correct method label; the recording catalog lacked that receipt.

`remote_yam.public_history` imports the existing public Site's physical receipts
into a dedicated cache. It requires matching top-level and result approach and
robot, a valid native episode, actual run-start timestamp and recorded runner.
It never infers the method from task text, images, model family or runner name.
Underlying inference IDs remain separate configuration. Private email, account
IDs, capabilities and provider settings are excluded. There is no model change
or policy/model test, so no new researcher model selection is needed.

Use the Site's existing supported service-access credential only for that exact
Site, according to Sites `identity-and-secrets.md`. Keep it in a private runtime
file outside source; never generate/rotate credentials merely to check access.
The reader rejects redirects, bounds the response and logs only error classes.
It makes a GET request and cannot start a robot or write to the Site.

Example host configuration (paths are operator-owned, not visitor input):

```sh
PYTHONPATH=/path/to/codex-runner/src python -m remote_yam.public_history \
  --origin https://blupe-bimanual-skills.andlyu.chatgpt.site \
  --approach RoboSkills --robot-id yam-1 \
  --database /var/lib/yam-web/roboskills-history/runs.sqlite3 \
  --token-file /private/runtime/path/roboskills-token
```

Run that metadata import periodically using the website's service manager, then
append this metadata-only source to existing `YAM_PUBLIC_RUN_SOURCES`:

```json
{"database":"/var/lib/yam-web/roboskills-history/runs.sqlite3","robot_id":"yam-1"}
```

Omitting `replay_root` keeps the archive's footage and outcomes authoritative.
Receipts without published footage are explicitly processing. Repeated imports
are idempotent; old receipts survive source paging or outages. The importer
refuses an unrelated database or a cache owned by another source.

Scoped checks:

- [x] Source provenance verified: public API returns 37 Site runs, including
  35 with native episode IDs; the known missing-label episode is present.
- [x] Offline tests exercise import, scope rejection, privacy, persistent/new
  receipts, existing outcomes, model filters and actual hosted HTTP projections.
- [x] Shared source published and deployed with an automatic metadata refresh.
- [x] Public catalog/filter and exact replay details show `RoboSkills`.
- [x] Retained replay still opens through the normal deployed UI.

## Deployed verification

[Shared PR258](https://github.com/andlyu/blupe-remote-bots/pull/258) merged as
`56bf2d1f7c3abda2ca389e8dd5c637ea49b6cb14`; its GitHub Shared runner check passed.
The isolated full server suite passed 1,403 tests, 181 subtests, with 100 skips
(794.665 seconds command wall time). Final focused checks passed 79 tests and
four subtests; 343 JavaScript checks passed.

At 2026-11-01T20:09:19Z the two metadata modules were deployed to the existing
BluPe website service. A GET-only systemd timer refreshes the dedicated public
receipt cache every 60 seconds. Existing Spotter source configuration and both
Spotter services were preserved. The website restart took 1.702 seconds after
all four robot queues were confirmed empty. No controller was restarted.

Public HTTP checks at 20:12:40Z found 35 RoboSkills runs in each of past-runs,
the table catalog and the cloud catalog. All 22 baseline Spotter IDs remained
present. The known native episode retained its recorded runner, successful
runner-reported outcome and exact existing quick-replay URL. That media returned
HTTP 206 for bytes 0–1023/22346. Underlying `inference_model=gpt-6-sol` remained
separate configuration, rather than becoming the approach label.

At approximately 20:37Z the normal public browser UI selected the RoboSkills
model filter, searched the historical fingertip task and opened
`ep_a41fd6cf5ebd402e`. Both its card and replay details displayed `RoboSkills`.
The retained 0.8-second quick preview played to 0.402298 seconds and sought to
0.2 seconds, with readyState 4 and no video error. This verifies retained-media
playback, not a new physical task or full-length recording qualification.

The hosting consumer retains its existing ASPIRE-compatible runner base. A
published backport, `d4e041638e4683834d7994cd5fb0e08507d4f0d5`, contains the reviewed
history fixes on base `5e63471875e021bfb51ebb281bb94b386c08a61e`; it avoids importing
unrelated native-control changes from shared main. Both metadata modules are
byte-identical to the deployed canonical fix. Hosting validation passed the
ownership check, 401 tests and 21 subtests (one skip, 62.610 seconds command wall
time), 77 focused shared tests and four subtests, 422 shared JavaScript tests
and 45 hosted JavaScript tests. The consumer update merged in
[hosting PR197](https://github.com/andlyu/blupe-evals/pull/197) as
`783b57234a4bf6b9b6ad1790a67b55e09fbfb80e`. Its GitHub hosted workflow did not
start any steps: the platform reported recent account payment failures or a
spending limit needing an increase (run `41347715749`). This was not a test
failure; the equivalent local suite and ownership check passed as above. No
repository protection or CI configuration was changed to merge the pin.

Deployed SHA-256:

- `integration_runs.py`: `d3be5988496571d497d7c28b596703d0adf476a5900d0fe31df00feccbdec17f`
- `public_history.py`: `d5e7e9ce2cfdf7bf79b8d6d998af024b1df31285c95a84a5424a3f0f31635992`

No physical run, identity submission, policy inference, camera recording or media
upload is performed. The specifically excluded historical recording remains
excluded; metadata import grants no permission to publish that clip. The broader
RoboSkills manipulation, every-run timing and final-UI qualification gaps in the
preserved integration checklist remain open; this is an attribution fix only.
