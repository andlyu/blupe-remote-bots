# Dream-1 in the playground

Dream-1 beta and Dream-1 beta Flash use the same bimanual YAM queue, lease,
trajectory validation and Stop path as the other shared policies. Selecting
Dream does not connect a second motor controller. Prompts remain editable.

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
SDK preparation begins in the controller's existing post-Home readiness gate,
so queued visitors consume no worker. Stop cancels a slot wait and releases an
owned worker. Local launch keeps its existing preparation behavior.

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
late response. After inference, motion retiming uses the latest valid measured
sample. These checks do not change Home, queue admission or lease behavior.

The SDK adds its YAM hand poses and uses Dream's current YAM default: the EEF
head with trajectory IK (`ik: {arm: yam, head: eef, solve: traj}`). It solves the
predicted hand poses into joint targets. After confirmed packet completion, the
bridge passes the final commanded target to the next SDK request so the seam
starts at the completed endpoint rather than an earlier row inferred from encoder
lag. Optional SDK background
recording is explicitly disabled. A changed prompt resets the SDK episode and
camera history. Model cold starts honor `pool_warming` retry delays, while Stop
remains cancellable. Session cleanup releases the Dream session on worker exit.

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
