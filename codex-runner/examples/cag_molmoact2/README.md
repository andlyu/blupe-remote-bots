# MolmoAct2 / CAG comparison case

This is a companion integration prepared in the shared runner repository. It
serves **the same** `allenai/MolmoAct2-BimanualYAM` weights in both modes, pinned
to `8dcbed66f2380e4393189c303ea72488eb9e63c2`. It targets **YAM1 only**;
Robo-house YAM has a different station configuration and is rejected.

The intervention is **`cag-inspired-molmoact2-v1`**, a paper-derived experimental
port, **not author code or an exact reproduction** of
[Completion Aware Guidance for World Action Models](https://arxiv.org/abs/2610.01559).
No official CAG implementation was located in the checked paper, author pages or
existing author correspondence. A changed action is evidence of an intervention,
not evidence of higher task success.

## Decision → reason → evidence

| Decision | Reason | Evidence / practical limit |
| --- | --- | --- |
| Public MolmoAct2 BimanualYAM release | User selected MolmoAct after a poor DreamZero trial; avoid an unrelated DreamZero checkpoint or an older ABC fine-tune | [Pinned model](https://huggingface.co/allenai/MolmoAct2-BimanualYAM/tree/8dcbed66f2380e4393189c303ea72488eb9e63c2); [official source](https://github.com/allenai/MolmoAct2/tree/6070080a20321b4f498ab30f28e1d09ac465edb7) |
| Hook the 36-layer action expert's cross-attention | Its projected vision/language K/V provides an accessible conditioning intervention | Pinned `modeling_molmoact2.py` SHA256 `3e0090b8cc045d59911c0a579815ebd17ce0423f9fdd03be887412df5c7b8b49`; `ActionExpertCrossAttention._attention`, `ActionExpert.prepare_context` |
| Top ceil(25%) of task tokens, all 36 layers, refresh each layer/flow step | The paper leaves selection/layers/refresh underspecified; these are explicit v1 experimental choices | `guidance.py` `SPEC`; task offset mapping fails closed when ambiguous; state/setup/control/image tokens are excluded |
| Current unmodified cross-attention scores averaged across heads/action queries | A deterministic, local ranking without another model prefill; differs from the original paper's global/layer pooling | Normalize over all valid context keys, rank eligible task tokens, stable token-order ties |
| Multiply selected post-normalization projected K and V by `1 + alpha` | A concrete conditioning-strength intervention | Alpha range 0–0.30, UI default 0.15; out-of-place scaling; non-task K/V checked unchanged on first attention call |
| Eager sampling in both modes, BF16, 10 flow steps, seed 0 per chunk | Python request hooks and CUDA graph replay are incompatible; keep both modes comparable | Worker readiness compares unpatched baseline, patched baseline and guided alpha 0 exactly; real GPU nonzero check must visit 36 layers × 10 steps |
| Separate authenticated RunPod load-balancing endpoint | Avoid replacing the existing baseline service or production Playground | Existing verified checkpoint/runtime volume is mounted; backend key never enters worker environment, browser or receipts |
| Existing BluPe controller/queue remains robot authority | Preserve leases, home/initialization, limits, cancellation and Stop | Adapter returns a validated chunk; it has no robot command transport; Run is user-initiated |

## Boundary and provenance

The policy receives exactly top/left/right JPEGs plus measured
`left six joints radians, left gripper, right six joints radians, right gripper`.
Grippers are normalized 0 closed / 1 open. Missing gripper measurements cause a
rejection, never an assumed value. Outputs are 30×14 absolute targets at 30 Hz;
rows 2, 5, …, 29 become ten 10 Hz gateway waypoints. Selected absolute targets are preserved. The adapter inserts linear samples
where needed to limit each100ms joint step to0.03rad; this retimes the same
path. It never clips targets or partially accepts a chunk. Downstream limits
remain authoritative, and the pacing is recorded identically for both modes.

Run configuration records checkpoint revision, variant, mode, strength, seed,
precision and sampler settings. Each inference receipt includes hashes of the
three images, state and instruction, timing, eligible/selected token counts,
visited layers, and K/V change evidence. Keep initial scene, instruction, time
limit and task outcome comparable manually; this demo does not reset scenes or
claim randomized evaluation. Each request's settings are fixed for that run.

`worker.py` and `bootstrap.py` extend the already measured local MolmoAct2 RunPod
prototype. The checkpoint code stays pristine. The digest-pinned CUDA image and
`requirements.txt` are checked against the prepared runtime receipt; executable
checkpoint assets are rehashed before loading. No credentials are bundled.

## Launch and lifecycle

From `codex-runner`, with its normal requirements installed:

```sh
PYTHONPATH=src python cag_molmoact_playground.py \
  --endpoint https://YOUR_ENDPOINT.api.runpod.ai --no-browser
```

The default URL is `http://127.0.0.1:8798`. Open the model menu, choose baseline
or the CAG variant, set strength, enter a task and press Run. Baseline forces
strength 0. `--preview` disables all robot runs. Only this launcher loads the
comparison controls; ordinary Playground users retain their normal UI.

The current launch command serves a local website with a remotely hosted model.
The ASGI app can be mounted behind a separately configured HTTPS host using the
existing Host/Origin/CSRF checks. Public website deployment, production replacement
and a public companion repository have not been performed by this example.

`deploy.py` requires an explicit existing prepared volume, a unique endpoint name,
and an external JSON state file. The volume must contain `molmoact2-yam/identity.json`
and its pinned HF assets, plus `molmoact2-runtime-local.tar.gz` (extracts to
`/opt/molmoact2-runtime`) and a checksum/requirements/image/revision receipt
`molmoact2-runtime-local.json`. Missing or mismatched preparation fails readiness.
No volume is created/deleted by this tool. The prepared cache is shared read-only
by convention; the application writes receipts under `/tmp`.

```sh
python examples/cag_molmoact2/deploy.py provision \
  --state /absolute/private/task-resources.json \
  --volume EXISTING_PREPARED_VOLUME --name UNIQUE_RESEARCH_TRIAL
python examples/cag_molmoact2/deploy.py start --state /absolute/private/task-resources.json
python examples/cag_molmoact2/deploy.py health --state /absolute/private/task-resources.json
# After verification, allow on-demand cold starts and 300-second idle shutdown:
python examples/cag_molmoact2/deploy.py release --state /absolute/private/task-resources.json
# Disable new GPU allocations immediately:
python examples/cag_molmoact2/deploy.py disable --state /absolute/private/task-resources.json
```

The detached backend guard is installed before paid workers start and disables
this exact endpoint at the original one-hour deadline; restarting does not reset
that deadline. Worker process lifetime is independently bounded. Keep the guard's
host awake. Inspect provider worker **and pod** state to confirm billing has
stopped; an IDLE logical worker alone is insufficient. Current provider pricing
must be read before launch; the October 29 trial observed $1.34/GPU-hour and LOW
US-CA-2 availability for the RTX 4090 pool. Existing volume storage is separate.

## Verification

CPU tests exercise exact zero-strength delegation, actual attention output
change, no cached/non-task K/V mutation, mask alignment/ambiguity, request cleanup,
robot/schema/receipt rejection, waypoint capacity, no-key session metadata and
pre-queue strength validation. Worker readiness adds real CUDA checks using the
checkpoint's documented images/state. `smoke.py` sends identical explicit inputs
in baseline/zero/nonzero modes, saves complete receipts and dispatches no robot
commands. It can be run with `PYTHONPATH=src` from `codex-runner`.

Live task success and physical safety depend on the existing robot/controller
checks and operator conditions; only physical trials can establish task outcomes.
The launch evidence and lifecycle state are stored outside the repository in the
current task's artifact directory, without credentials.


## Harness attribution and deployment

`CAGPlayground` now requires each human to confirm an editable name and email.
Known values from this website's browser storage are prefilled; a new browser
starts blank. Emails stay in private queue/contact records, while public run
context carries the confirmed name, human/automated kind and confirmation flag.
Automated clients send `runner_kind: "automated"`, omit email, and are labelled
`Automated CAG test`; they require no interactive signup. Existing visitor,
Origin and CSRF checks apply to both kinds of client.

Each run's frozen configuration and interaction record include the actual
baseline/guided approach, variant, strength and runner. The model label names
the approach being executed. The dedicated website defaults to YAM1 and does
not offer a different station for this checkpoint.

For hosted ASGI deployment use `cag_molmoact_playground:create_app --factory`
with `CAG_PUBLIC_ORIGIN`, `CAG_MODEL_ENDPOINT` and `CAG_RUNPOD_KEY_FILE`.
`CAG_SESSION_API` defaults to BluPe's public Session API. Set
`CAG_RUNS_ENABLED=1` only when the model deployment is ready; otherwise the
website explicitly reports paused inference and rejects Run before preparation
or queue creation. This is a service availability setting, with no change to
robot/controller limits. Never expose the model credential to the browser.

The companion website source pins this shared runner rather than copying it.
See its integration completion checklist for deployed source, current evidence,
physical-run status and the two required 15-second measurements. Offline tests,
prior CUDA results and accepted commands do not verify actual physical motion.


## Persistent website service

The live CAG website uses an on-demand deployment rather than a time-limited
trial. Its private service state has `mode: "on_demand"` and no `deadline`.
After confirming the previous trial guards have completed and the endpoint has
zero active workers, `deploy.py serve --state /absolute/private/service.json`
updates that same owned endpoint, permits one worker maximum, and scales to zero
after300idle seconds. It disables the trial worker lifetime. The original trial
record and its fixed deadline must be retained unchanged. Persistent availability
is explicitly authorized separately from a trial; there is no automatic trial
renewal.

Run starts model preparation before queue admission. The page reports elapsed
GPU startup, queue waiting, robot preparation, and execution as separate states.
Stop cancels GPU preparation before creating a robot session. The configured
recording filesystem must pass its existing controller check before a physical
session; GPU readiness alone is not a robot-readiness guarantee.
