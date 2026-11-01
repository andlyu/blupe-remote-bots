# Public integration runs in BluPe history

Integrations can use the same robot queue/backend while retaining their own run
receipts and quick replay cache. The public dataset alone does not list these
receipts before archive publication. Configure the shared runner to read those
existing stores on the website host:

```sh
YAM_PUBLIC_RUN_SOURCES='[{"database":"/home/ubuntu/blupe-spotter/blupe/vendor/remote-yam/codex-runner/data/run-names.sqlite3","replay_root":"/home/ubuntu/.cache/blupe-spotter-replays","robot_id":"robot-ba8413962083809c"}]'
```

This is an operator setting, never visitor-supplied input. Each source is scoped
to its configured robot. SQLite reads use `mode=ro`; missing stores are not
created. Run metadata, recorded method/model, public runner name and recorded
result are projected. Email, social handles, credentials and other configuration
fields are excluded. The integration remains the owner of its data.

The same merged catalog supplies Past Runs, model/task filters, the table/cloud
catalog and episode lookup. Receipts refresh on each request, independently of
the remote archive cache. Matching episode IDs are deduplicated; the receipt
preserves the actual method and runner. A missing replay remains explicitly
processing. A ready replay replaces that state without changing the episode ID.
An archive outage leaves the integration receipts available with `stale: true`.

Media is served at `/api/integration-replays/<episode>/<sha256>.mp4` on the main
website origin. Only a receipt for the configured robot plus matching replay
metadata can expose a file. Size, immutable digest, path and camera/duration
metadata are checked; serving verifies the SHA-256 and supports byte ranges for
native seeking. The default policy permits same-origin media. There are no
cross-origin media dependencies, copied recordings or new robot commands.

Verification: `python -m pytest codex-runner/tests/test_integration_runs.py -q`
exercises the real hosted catalog/detail/media routes and the archive reader,
including fresh receipts, deduplication, privacy projection, archive failure,
station scope, hashes and byte ranges. It starts no robot or model inference.

Invocation: “When we reun spotter, these runs should also show up in blupe”,
followed by “right, but dont' we have access to spotter's runs throguh blupe?”
The user-adopted shared harness selects the playground-fix workflow. Its
“Authorization granted by using this harness” contract covers public source
delivery and website updates. Scope: `https://playground.blupe.io`, existing
`https://robohouse.spotter.54.209.185.15.sslip.io` public run stores and
`https://github.com/andlyu/blupe-remote-bots`. This fix uses retained runs; no
physical execution, identity submission or underlying model change is required.
