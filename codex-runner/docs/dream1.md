# Dream-1 in the playground

Dream-1 beta and Dream-1 beta Flash use the same bimanual YAM queue, lease,
trajectory validation and Stop path as the other shared policies. Selecting
Dream does not connect a second motor controller. Prompts remain editable.

SDK protocol failures preserve only a static category (non-JSON reply, missing
status envelope, connection failure, or other protocol error), safe HTTP status
when present, an allowlisted cause type, command phase and numeric timing fields.
The interaction journal and user error retain that category; raw SDK messages,
endpoints and response bodies are excluded. Protocol errors stop the run without
an added inference retry. Historical failures recorded before this diagnostic
change cannot be classified retrospectively from their exception type alone.

SDK1.0.0 on Linux/OpenSSL3.0 can raise `SSLEOFError` when reusing an idle TLS
connection; its stale-connection retry handles several other socket errors but
does not cover this subclass. A loopback TLS reproduction against the exact
installed transport failed for idle reused connections at both small and large
body sizes, while fresh connections passed through800KB. This does not establish
a remote request-size limit or retrospectively recover a discarded cause.

The bridge now drops only the SDK's HTTP channel before/after prediction and
episode reset. The logical model session, camera window, smoothing/command
anchors and compiled solver remain intact. Each prediction still makes its
ordinary request; no new inference retry is added. This incurs a fresh TCP/TLS
connection per exchange; remote handshake overhead has not been measured by the
local reproduction. Endpoint configuration and certificate verification remain.

Protocol diagnostics retain bounded TLS/HTTP subclass names or a safe base
family, numeric errno, allowlisted SSL reason and transport stage. At most eight
allowlisted module/function/line entries can identify send, response headers,
response body, decoding or envelope validation. They include no filenames,
frame locals, SDK message text, headers, bodies, endpoints or credentials.
`http_connection_policy=fresh_per_exchange` identifies the new channel policy.
See [Python HTTP/TLS contract](refs/python/HTTP-TLS.md).

### Tracking a prediction that does not return

The worker writes `sdk-trace.jsonl` in its `DREAM_WORK_DIR`, alongside the
existing `stage-timings.jsonl`. Deploy `dream_sdk_trace.py` beside
`dream_worker.py`; it uses only the standard library. These private diagnostics
persist independently of the worker's stdout reply, including when the parent
terminates a prediction at its thirty-second deadline.

Fixed stages identify observation forward kinematics, HTTP exchange, lazy
connection setup (DNS/TCP/TLS together), sending, response headers, response body,
local IK and smoothing. Each records start/completion/error. While a prediction
is active, a separate monitor samples every five seconds and records the
innermost active stage, elapsed durations and at most eight allowlisted static
module/function/line frames. Match wall timestamps and the numeric first step
to the visitor journal; a process-local prediction number and PID distinguish
calls and replacement workers. Completed HTTP is a client transport boundary,
not evidence of the server's internal inference timing.

The prediction thread only enqueues fixed labels and numbers. A daemon writes
owner-only files, rotating at 2 MiB with one backup; a bounded 128-row queue
drops diagnostics if storage stalls. Records include dropped/write-error
counters. There are no bodies, frames, prompts, state arrays, headers, endpoint
addresses, remote session identifiers, exception text, filenames or frame locals.
Sampling requires the Python interpreter to schedule the monitor; a native
operation holding the GIL can prevent fresh samples. Missing/truncated traces
or writer failures remain inconclusive. This telemetry does not change the
prediction deadline, retries, returned action or worker recovery behavior.

The pinned SDK's fifteen-second transport setting is a socket timeout, rather
than an overall prediction deadline. In an offline TLS loopback test, a silent
response timed out at fifteen seconds, while headers or body arriving in pieces
less than fifteen seconds apart kept the exact transport active past thirty
seconds. Local IK also runs outside the transport timeout. Those tests explain
possible timeout paths; they do not identify the cause of an earlier run whose
only recorded boundary was `sdk_get_action` starting.

## Setup

Create a separate Python 3.12 environment and install
`codex-runner/requirements-dream.txt`. Keep the normal playground environment;
the optional SDK runs in a subprocess selected by `YAM_DREAM_PYTHON`.

Save the credentials from Dream Labs' Setup API page to
`~/.dreamlabs/credentials` with owner-only permissions. Never put the key in
source, browser fields, command-line arguments or a committed environment file.

For local launch, set:

```sh
export YAM_DREAM_PYTHON=/absolute/path/to/dream-venv/bin/python
export YAM_DREAM_CREDENTIALS="$HOME/.dreamlabs/credentials"
./codex-runner/run.sh --provider dream --session-api https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com
```

The local launcher also discovers the default credentials file automatically.
Set `YAM_DREAM_CREDENTIALS` to an empty string to disable that discovery.
The command above runs from the repository root and opens the local playground;
entering a prompt and clicking Run joins the physical robot queue.
Choose **Dream-1 beta** or **Dream-1 beta Flash** in the provider picker.
Both options require account access to the matching checkpoint. This does not
use a ChatGPT/Codex subscription; inference is funded by the configured Dream key.

Hosted deployments must explicitly set both `YAM_DREAM_CREDENTIALS` (a private
file on the server) and `YAM_DREAM_PYTHON`. The hosted application retains its
existing guest allowance. Credentials and local paths are excluded from public
session metadata and model configuration.

On a small hosted fleet, pass one shared `threading.BoundedSemaphore` as
`dream_worker_pool` to bound SDK/IK processes across stations. With a pool,
SDK preparation begins after lease grant, so it can overlap native Home while
queued visitors consume no worker. Stop cancels a slot wait and releases an
owned worker. Local launch keeps its existing preparation behavior.

For server-wide compiled-solver reuse, explicitly set
`JAX_COMPILATION_CACHE_DIR` to a persistent, service-owned directory. The worker
honors that path across distinct visitor processes; without it, the fallback
remains the visitor's private SDK work directory plus `jax`. SDK sessions,
observation history and commanded targets remain private to each worker. No
observation or prediction is needed to prepare the local solver through SDK
policy configuration.

Protect the cache directory with0700 permissions and trust every writer. JAX
keys compiled executables by computation HLO, jaxlib version, relevant XLA flags
and device configuration. Deployment must track SDK source/runtime and robot/IK
configuration compatibility, prewarm invalidated configurations before exposing
Dream as ready, and retain compatible artifacts across release paths/restarts.
The cache avoids repeated compilation work; Python imports, graph tracing,
model-record retrieval and per-session setup can remain. Measure fresh processes
and background trajectory readiness rather than treating a populated directory
as proof of instant readiness. See the [pinned JAX guide](refs/jax/INDEX.md).

For preparation reused in memory across visitors, a hosted fleet can create one
`remote_yam.dream_worker_pool.DreamWorkerPool(python, credentials, directory)`.
Call `prime()` before advertising Dream. It prepares both supported checkpoints
and waits for each pinned SDK trajectory-ready event in one SDK process. Supply
the same pool's `factory` as `dream_worker_factory` on all hosted robot apps,
and `lambda: pool.status()['ready']` as `dream_worker_ready`. Retain the existing
shared `dream_worker_pool` semaphore; queued visitors acquire no worker handle.
SDK policy construction, graph tracing and compilation occur at preparation,
not when a visitor selects an already prepared checkpoint.

Each visitor receives an exclusive handle. The SDK's documented
`reset_episode()` ends the previous remote model session, empties its image and
observation window, and resets chunk blending. Handles clear the worker's
timestamp and keep adapter history/commanded targets private to the visitor.
Each checkpoint retains its own prepared SDK policy and static IK configuration.
Different interpreters or changed credential files cannot borrow the worker.

Stop returns without waiting for a pending SDK reply. One serial task drains
that reply and resets the SDK before the next visitor can acquire ownership;
the late result cannot enter a new visitor's call. The adapter's existing
semaphore releases promptly. Reset/transport failure discards the worker and
removes readiness while a replacement prepares. Public configuration hides unready Dream models and forged run requests
are rejected before queue creation. Shut the pool down with `close()` on service
shutdown. Keep the persistent JAX cache for compatible service restarts, prepare
once per new process, and retain the one-process memory budget. Actual prediction
continues after confirmed Home with fresh inputs and normal native guards.

The prepared pool replaces an idle dead worker without acquiring a robot session
or making a prediction. Background replacement backs off by 1, 10 and 30 seconds.
At most three replacement attempts are allowed in a ten-minute burst, and three
consecutive failed preparations also open the circuit even outside that window; exhaustion
leaves Dream unavailable until explicit preparation/restart. Changed credentials
also require explicit preparation. The old child exits before a new one starts;
both checkpoints must be ready and episode cleanup must pass before admission.

An active run can recover one discarded worker while retaining its exclusive
visitor owner. The replacement starts a fresh SDK session. Before requesting a
new action, the controller verifies the same robot lease, completed step and idle
executor; the adapter clears prior command anchors and camera history, discards
in-flight captures from the old history generation, and waits for feedback/images
collected after recovery. The failed prediction is never submitted or replayed.
Run step IDs continue normally. Stop and the original run deadline still cancel
recovery and prevent submission, including after a late preparation result.
Recovery consumes the remaining time budget and can outlast it; it does not imply
uninterrupted motion or establish why the original SDK call stalled. A second
worker failure in the same run ends that run. Returned SDK protocol errors retain
their existing fail-closed behavior.

The run journal records bounded `worker_recovery` transitions and model status
messages. Service logs use `[dream-worker]` for failures, preparation and recovery
limit events, with static reasons and numeric attempts only. Readiness proves
preparation, not successful inference.

## Observation and execution contract

The adapter polls measured state and all three camera views at up to 5 Hz while
the run is active, including during trajectory playback and inference. It keeps
the most recent nine actual camera ticks. Captures that take longer reduce the
achieved rate; frames are never duplicated to manufacture history. Capture
timestamps use the collector's monotonic clock. Overhead, left-wrist and
right-wrist views are resized to 320x176 JPEG quality 85. Joint state is converted
from degrees to radians and grippers retain their closed=0/open=1 convention.
Finite predicted grippers are clipped to [0, 1], matching the official SDK robot
adapter; its chunk smoothing can slightly overshoot the open/closed endpoints.
Raw gripper range and clipping counts are retained in the model timing journal.
The idle, unopened hardware reports null grippers. Dream waits for the runner's
normal launch/home sequence before collecting inputs. Missing measurements, stale
state, or state that expires during capture invalidate the current history and
allow up to five seconds of recovery with new measured samples. Persistent gaps
fail with the affected field named. Malformed values, nonfinite values, wrong
robot identity and invalid camera sets fail immediately; no commanded values
replace missing measurements. A capture failure during inference discards the
late response. If camera retries outlast the original state sample, the adapter
reads measured state again and pairs it with the recovered complete camera set.
Expired frames and invalid or missing remeasured state still cannot be used.
Camera retry logs retain the role, HTTP status and attempt; the camera transport
keeps its existing bounded retries, separate from the five-second feedback
recovery window. After inference, motion retiming uses the latest valid measured
sample. These checks do not change Home, queue admission or lease behavior.

The SDK adds its YAM hand poses and uses Dream's current YAM default: the EEF
head with trajectory IK (`ik: {arm: yam, head: eef, solve: traj}`). It solves the
predicted hand poses into joint targets. After confirmed packet completion, the
bridge passes the final commanded target to the next SDK request so the seam
starts at the completed endpoint rather than an earlier row inferred from encoder
lag. Optional SDK background
recording is explicitly disabled. A changed prompt resets the SDK episode and
camera history. Model cold starts honor `pool_warming` retry delays, while Stop
remains cancellable. Session cleanup releases the Dream session on worker exit. If the SDK reports
`DreamSessionExpired` / `DA-0001`, it has already adopted a replacement model
session and discarded that response. The bridge requests one new prediction
from a new camera/state tick; it does not replay a packet, restart Home or alter
the robot lease/step IDs. A second replacement during that decision fails. Stop
can cancel the recovery, and authentication errors do not retry. Logs retain
allowlisted code/reason/type fields without server text or session identifiers.

The existing runner executes one packet to completion before asking for the
next. Dream chunks at the configured 20 Hz are sampled at their 100 ms endpoints
(indices 1, 3, ...), converted back to degrees, and sent as 10 Hz packets. A
48-row chunk initially becomes 24 waypoints covering 2.4 seconds. The model menu's
**Joint motion cap** displays a fixed 20 degrees per 100 ms (200 degrees/s).
It is owned by the runner; browser users and run-request payloads cannot change it.
When a segment exceeds that cap, the backend inserts synchronized linear
waypoints for both arms and grippers, extending its duration and preserving every
sampled target. Known station profiles also apply their lower step/velocity cap;
YAM-1's profile currently allows 9 degrees per 100 ms. These limits are shown in
the model menu, and requested/effective caps plus inserted-point counts are
journaled per packet. The first segment starts from measured feedback. Gateway
joint positions, workspace, collision and motor checks still validate the full
packet. Packet/session waypoint budgets remain enforced. Physical trajectory
fidelity and task performance still need validation. This initial integration
does not implement asynchronous chunk refill.

The worker has no Session API or motor access. Late responses are discarded on
cancellation and the existing controller also verifies the active lease before
dispatch. SDK errors expose types/status codes rather than request or credential
text. SDK 1.0.0 is pinned because this bridge depends on its documented state,
camera and action contracts.

## SDK preparation and Home ordering

Hosted queue admission alone starts no heavy SDK process. The canonical
`jetson_leased` event (which has no lease_id in its payload), or an already-leased
reconnect snapshot, starts cancellable SDK preparation under the existing single
worker slot. This lets setup overlap native Home. The ordinary first-observation
path still waits for SDK readiness, validates the same live lease/step, reconciles
confirmed Home feedback and supplies fresh measured state/images before prediction.
No saved-Home speculation, synthetic homed state or early Dream request is added.
Astra's saved-scene protocol remains ineligible for Dream. See the pinned
[startup/observation contract reference](refs/dreamlabs/STARTUP-CONTRACT.md).

`policy_timing` events separate lease preparation scheduling, worker acquisition,
worker creation/configuration, readiness wait, lease/feedback refresh, Home report
arrival, confirmed Home feedback, selected camera/state/encoding cost and prediction.
Child timings separate SDK imports, client construction, policy configuration,
observation update and get_action. Parent/worker wall timestamps are from the same
host and durations use monotonic clocks. Native observation timestamps are labeled
separately; lease scheduling/Home-report arrival are not physical motor-start times.

The worker also appends protected `stage-timings.jsonl` in its existing SDK working
directory, including stage starts before a long configuration. Those boundaries
survive Stop before a command reply; stdout retains exactly one JSON response per
command. No prompts, frames, joints, endpoints, credentials or arbitrary SDK text
enter timing rows. Camera boundaries are emitted only for the first capture, with
numeric summaries for the selected sample per prediction, avoiding 5 Hz journal spam.

The earlier45.366 s readiness/revalidation interval is not retrospectively split
by this change. A later user-initiated run must establish actual startup phase
durations and the amount of Home overlap. There is no fixed45-second sleep. The
separate third-request protocol failure and all motion/Stop/native checks remain
unchanged.

## Duration and recorded replay pacing

New beta and Flash launches default to 120 seconds and accept 60–120 seconds.
The server rejects longer or noninteger durations before queue admission. The
UI offers one or two minutes and preserves other providers' duration choices.
The selected limit reaches the existing session/native timeout path.

Saved run configuration exposes only an episode's replay pacing (Dream 2×, other
providers 10×), without exposing the saved configuration or credentials.
A publisher must match both episode and robot before encoding a new Dream clip.
Missing identity defers publication. Current motion/idle selection and quality
metadata are independent of pacing. The cache adapter reports actual encoded
speed: new 2× clips play at 1×, legacy 10× Dream clips at 0.2×. Original full-timing
recordings remain available through the existing Live speed option.
