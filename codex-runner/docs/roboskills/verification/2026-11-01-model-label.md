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
- [ ] Shared source published and deployed with an automatic metadata refresh.
- [ ] Public catalog/filter and exact replay details show `RoboSkills`.
- [ ] Retained replay still opens through the normal deployed UI.

No physical run, identity submission, policy inference, camera recording or media
upload is performed. The specifically excluded historical recording remains
excluded; metadata import grants no permission to publish that clip. The broader
RoboSkills manipulation, every-run timing and final-UI qualification gaps in the
preserved integration checklist remain open; this is an attribution fix only.
