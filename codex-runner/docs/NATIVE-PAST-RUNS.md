# Native station Past Runs

The station mode uses the same recording-block Table, 3D Cloud, assessment overlay,
revision votes and five-second review window as the shared playground. It reads
native recordings instead of substituting public history or uploading local data.
The station adapter and terminal credential helper were previously packaged from
unpublished shared working-tree source; they are now part of this repository.

## Launch and deployment contract

Use the existing station UI service and loopback coordinator. Do not replace or
restart the coordinator/controller as part of this app update. The runtime needs
Python 3.11+ for the current pinned SciPy, the runner requirements (including
sentence-transformers 5.1.2), and a local `ffmpeg` with the `libx264` encoder. On
ARM, install a compatible CPU PyTorch build in the existing isolated environment;
wheel resolution or source tests alone are not proof of native execution.

```sh
python codex-runner/run.py --station-local --station-provider codex \
  --session-api http://127.0.0.1:8000 --camera-origin http://127.0.0.1:8089 \
  --recording-root /absolute/durable/app-state \
  --station-episodes-root /absolute/native-episodes \
  --station-media-cache /absolute/durable/native-media-cache --no-browser
```

Retain the station's existing `--station-provider` and credential configuration;
Past Runs itself does not require provider login, an API key, or a robot session.
The service still binds only `127.0.0.1` (default port 8787), validates Host and
Origin, and keeps the station's self-only browser media/connect CSP. A temporary
SSH forward for browser verification must preserve the configured Host/port.
Existing operator/status and session/camera transports stay on loopback. No new
listener, public upload, account requirement, motor enable or motion check is
introduced. Existing run controls and gateway checks remain authoritative.

`--station-episodes-root` may be repeated. Configure the recorder roots containing
`ep_*/manifest.json`, `samples.jsonl` and either loose `images/<camera>-<frame>.jpg`
files or the recorder's `direct_usb_tar` format (`images_archive: images.tar`,
with those same relative JPEG members inside the uncompressed archive); do not point
at model log folders or public dataset exports. Each episode ID must identify one
recording across the configured roots. Native source directories and samples are
read-only to this feature. The media cache must be separate from those roots and
empty on first use; a marker establishes that only generated cache files may be
evicted. Use a native filesystem for app state, SQLite, model cache and environment
(some external NTFS/FUSE mounts lack required filesystem semantics).

Persist `YAM_ASSESSMENT_DATABASE`, `YAM_TASK_CLOUD_DATABASE` and the adjacent
`task-model/` cache. Their defaults live below `--recording-root`, alongside the
existing run-name/submission journals. Keep those paths stable across versioned
UI service upgrades. The app's private `.station-user` identity also remains there:
real controller-associated runs record this local application's user identity, so
labels remain editable across browser/service restarts by that same local user.
This is a single-user loopback application, not a multi-user hosted identity
provider. Vote identity remains browser-session based; the originating session
cannot vote on its own assessment. Historical ownership or success is never seeded.

## Catalog, replay and privacy

The native catalog projects only episode ID, robot, task, recorded model/version,
start time and machine-ending metadata. It uses the existing model journal when
available, leaves missing models unknown, and never turns machine endings into
human labels. Full filtered scores and stable task coordinates are unchanged.
Metadata listing does not read images or encode every episode. Native media detail
is requested for the visible Table blocks, a hovered/focused point, or full replay.

Finalized recordings are encoded lazily in one background worker, with a process
lock for overlapping UI candidates. The renderer reads only allowlisted native
JPEG paths and rejects symlink traversal. TAR recordings are opened/indexed once
per render and read with `extractfile`, without extracting or modifying sources.
Members must have unique allowlisted names, regular nonsparse file types and
bounded sizes; links, traversal, duplicates and oversized frames are rejected.
It preserves recorded timestamp gaps
at the recorded frame rate, composes the existing main/side-camera hierarchy and
writes H.264 MP4 with fast start. The fast preview uses the shared playback-speed
helper; **Live speed** plays the same original-timing file at 1x with pauses.
There is no second native encode or idle-removal claim. A finalization receipt
rechecks the selected manifest immediately, allowing preparation to overlap the
existing five-second assessment window. Pending blocks/hover previews retry with
cancellation; unavailable recordings remain truthful and details stay accessible.

The marked cache is bounded to 1 GiB, with a 256 MiB per-encode output limit and
a free-space guard. Only reproducible cache MP4/receipt files are evicted; source
recordings, model logs and assessment/index databases are never deleted. Media is
served in bounded chunks with HTTP byte ranges through opaque, catalog-bound
`/api/native-runs/<episode>/<fingerprint>.mp4` URLs. Arbitrary files, model artifacts,
external viewer/history proxies and cross-origin media requests are not served.

## Validation and rollout

Shared tests exercise native recorder-schema fixtures, actual H.264 encoding and
pause duration, lazy caching/restart, range/Host/Origin/traversal boundaries,
no-network/no-admission behavior, durable assessment revisions and unscored votes
without coordinate changes. Those fixtures are temporary test data, not production
evaluation results. The hosted mode's defaults and public catalog are unchanged.

Package the shared config/task-cloud-projection-v1.json, new native history/station
modules and unchanged shared static assets together; do not replace only a Python
file in the old packaged release. Prewarm using the service
YAM_TASK_CLOUD_DATABASE path:

```sh
python codex-runner/tools/prewarm_station_history.py \
  --episodes-root /absolute/native-episodes \
  --media-cache /absolute/durable/native-media-cache \
  --database /absolute/durable/task-cloud.sqlite3
```

This command never starts a robot session or encodes the video library; it prints
only counts, projection version and runtime. On a cold nonempty native index,
`native_encoder_executed: true` and `encoded_tasks` record successful encoder
calls; a warm index can truthfully report false/zero. Run it again in a fresh
process to check the persisted coordinates without treating an empty catalog as
native acceptance.

Before activating the candidate UI service, its deployment owner must verify the
real ARM encoder and ffmpeg, prewarm the real native catalog in the same durable
index path, restart a separate process to check stable coordinates, and play an
actual native preview and 1x replay. Preserve installed station overlays, provider
settings, rollback package and existing Codex runtime/TMPDIR service drop-ins. Only
that owner updates private packaging/pins and the inactive UI service. No local
fixture labels, votes, fake model names or test databases belong in production.
