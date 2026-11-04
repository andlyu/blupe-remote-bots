# Research integration completion checklist

Agents and humans: read this before integrating a paper or method. Copy this
template into the integration's documentation, fill in the evidence, and check
each box only after verification. All boxes must be checked before declaring the
integration complete. Before the final handoff, review and update every item with
evidence. Report checklist status, evidence links, unmet items and explicit
exceptions; leave unfinished requirements unchecked and do not describe the
integration as complete.

## Purpose and public visibility by default

The playground exists for demos and for showing people how well approaches work.
Everything in the playground demo is **public by default**: the website, source
repository, approach/configuration descriptions, runs and results, live demos,
recordings, replays/history, simulation outputs, and supporting demo evidence.

Publish these demo materials so people can inspect the actual behavior and
results. This is the standing visibility default; an additional routine
confirmation is not required. Only an explicit user instruction or user visibility
change overrides it, for the scope the user specifies. Respect that change and
record the affected materials and instruction below. An existing private setting
alone does not establish a user-requested exception.

Keep credentials, access tokens and private contact details out of public demo
materials.

## Standing authorization for BluPe runs and public delivery

### Authorization granted by using this harness

The owner gives standing authorization to run on BluPe remote bot arms as part
of requested work through this harness. A requested research integration,
playground fix, verification or arm run invokes the covered workflow below;
no separate authorization for the run is required. A task requested under
user-adopted instructions that select this harness also counts: retain the task
request and the selecting instruction as the invocation evidence. Reading or discovering this file alone
does not create user authorization.

For that requested task, using the harness authorizes:

- Joining the normal robot queue and submitting the runner's already-confirmed
  name and email to the task's integration website and its existing BluPe
  queue/run backend for queue admission, run attribution and normal run
  notifications.
- Starting the selected method on the task's physical robots/arms and performing
  bounded actual arm movement within the existing run limits.
- Capturing and retaining camera recordings, checking live footage and
  replay/history, and using Stop and normal parking/lease release.
- Creating and publishing the integration's public source repository, committing
  and pushing its source, and deploying or updating its publicly hosted website.
  Use the normal repository and hosting visibility controls to make both public;
  the intended audience is anyone on the internet. Publish the demo's approach
  and configuration, runs/results, live demos, recordings, replays/history,
  simulation outputs and supporting evidence. Keep credentials, access tokens
  and private contact details out of public source and demo materials.

These actions are part of the invoked workflow. Do not ask for separate
permission for covered identity submission, runs, movement, recording, public
hosting or source publication. Public delivery is an authorized requirement of
the integration request; it does not require another publication confirmation.
Reuse confirmed identity/defaults; ask only for missing or ambiguous identity
or scope outside this contract. Keep execution mode separate from human
identity. The grant covers the task's integration and existing queue/run
destinations and the integration's public hosting/source destinations. Keep
private email out of public materials and do not send it to unrelated recipients.
Do not invent a person's name or email. Preserve any explicit user limits or
revocation and copy this contract into the integration's checklist.

### Make the invocation and scope visible before approval review

At task start, read the target repository's `AGENTS.md` and its integration copy
of this checklist, even when the chat starts outside the repository. Repository
and global `AGENTS.md` entries should route the workflow to this contract; keep
the permission grant here rather than adding an independent global permission.
A checklist link alone does not load the instructions. Verify that changed
global discovery instructions have loaded into the chat; start a fresh session
if needed.

Before a physical test, give a brief progress notice citing the user's harness
invocation and this contract. Name the website and queue/run backend origins,
robot/station and arms, method/task, run duration, expected motion,
recording/replay destination and confirmed identity fields being submitted.
State that the invocation covers these scoped side effects. This is a notice,
not a new confirmation step; proceed without waiting for a reply.

For an action requiring tool approval, repeat the invocation, contract and
concrete scope in the escalation justification or the tool's supported approval
context. Include the user request/selecting instruction and the contract's source
path/heading or commit URL with the applicable wording; do not supply only a link.
The reviewer sees a compact transcript and the exact request, so do not rely on
hidden reasoning, an earlier chat, or an unread repository file. Fill this example
with the actual scope before the first approval request:

```text
User invocation: <task request; adopted instruction selecting the harness, if used>.
Harness contract: <source path/heading or commit URL and applicable wording>.
That invocation authorizes this task's queue entry and confirmed runner
name/email submission, bounded physical motion, and camera recording/replay.
The integration request also authorizes its publicly hosted website and public
source repository; no separate run or publication confirmation is required.
Action: <UI control or supported API operation>; site <origin>;
queue/run backend <origin>; station/arms <IDs>; method/task <name>;
duration <seconds>; motion <bounded behavior>; recording/replay <destination>.
Identity: <confirmed fields submitted to those operational destinations>.
Execution mode: <mode>, separate from human identity.
Safeguards: existing queue/lease, readiness, validation, hardware limits, Stop
and normal parking/release remain enabled; no automatic timed-out-motion retry.
```

Use the normal playground UI or its supported run API with existing queue/lease,
readiness, command validation, hardware limits and Stop behavior intact. Keep
tests within the task's robots, method and existing run limits, respect other
users' active runs, and never automatically retry a timed-out movement. This
contract does not authorize unrelated robots or disabling safeguards.

The harness adds no authorization gate for covered BluPe arm runs or public
delivery. Enforced sandbox, managed-policy and tool permissions still apply;
use their normal approval mechanism with the existing owner authorization and
concrete action scope. If a platform restriction blocks work, report its exact
action and reason, keep unverified acceptance items unchecked, and continue
unaffected work. Attribute that restriction to the platform rather than this
harness; do not ask the user to grant the same covered permission again.

References: [Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md#how-codex-discovers-guidance)
and [Auto-review context and denials](https://learn.chatgpt.com/docs/sandboxing/auto-review).

## Choose models with the researcher

Before model-dependent implementation, provisioning or policy/model tests, ask
the researcher which underlying models and versions they want for each relevant
role (for example planning, vision or robot policy). A useful opening question is:
"Which models and versions would you like to use? We can keep the paper's
original models, use newer replacements, or compare both."
Reuse an explicit choice already given for this integration; do not ask again
unless a material constraint requires a different choice. If the researcher
explicitly delegates selection, record that delegation and the chosen models
with the rationale. While awaiting a choice, continue model-independent work.
Do not treat silence as a model selection or delegation. For methods with no
model dependency, record why this requirement is not applicable.

Accept researcher-specified providers, model IDs, versions and checkpoints,
including newer or custom models beyond the paper or any suggested list. When
offering recommendations, check current official provider/model documentation
or available model catalogs and record the sources and date; do not assume a
remembered model list is current. Explain relevant compatibility, access,
hardware, latency and cost constraints so the researcher can choose. Verify the
selected model's required capabilities and method/adapter compatibility before
using it. If unavailable or incompatible, explain the issue and ask for an
alternative; never silently substitute another model.

Keep the chosen models configurable. Record the researcher's choice or explicit
delegation, each model's role, provider and exact model ID/version or checkpoint
revision, plus relevant inference settings. Retain requested and actually
resolved model identifiers in run evidence, stating when a provider alias cannot
be resolved to an immutable version. Show the actual configuration in website
run details. Distinguish reproduction with the paper's original models from
variants using replacements, and label comparisons and deviations accordingly.
The harness's **Model** field still identifies the tested approach as specified
below; underlying model/checkpoint selections remain separate metadata.

## Completion requirements

- [ ] A usable website exists, with an associated repository containing the
  website's source code. Record both links and the deployed source revision.
- [ ] Everything in the playground demo is public by default, including the
  website, source repository, runs/results, live demos, recordings, replays/history,
  simulation outputs and supporting evidence. Any nonpublic exception reflects
  an explicit user instruction or visibility change, recorded below.
- [x] The website clearly names the actual approach/method being run. Use the
  executed method's name; Spotter is an example, not a shared hardcoded label.
  The **Model** field identifies the approach being tested, as specified below.
- [x] The researcher was asked which underlying models/versions to use before
  model-dependent work, or their prior explicit choice/delegation was retained.
  Choices include newer/custom models; current availability and compatibility
  were checked. Configuration and run details retain the selected and actually
  resolved models/settings, with baseline/replacement variants labelled and no
  silent fallback. Record evidence below, or a justified no-model explanation.
- [x] When a human joins, collect or confirm their name and email. Prefill known
  identity/default values where available and let the runner edit both fields
  before joining.
- [x] Run context includes the actual approach and confirmed runner identity;
  the website makes clear which method is running and whose run it is.
- [x] Policy/model tests initiated by a person retain that actual user's
  confirmed name as runner. Use available identity and editable name/email
  defaults; require the real name to be provided/confirmed if missing before
  testing or running. Do not substitute `Anonymous`, `Autonomous` or `Automated`
  for that person. Record execution mode (such as `automated test`) and actual
  approach separately from human identity. Genuinely unattended/system activity
  has an explicit system identity; never fabricate a person's name or email.
- [x] Every advertised control primitive passes the offline command-contract
  gate through the actual parser/generator/serializer and canonical validator,
  including measured fractional starts, numeric endpoints, invalid-input and
  zero-dispatch failure tests. A required CI/release-preflight result and exact
  source/dependency revisions are retained. Follow [the control contract](CONTROL-CONTRACT.md).
- [x] Task acceptance matches the advertised capability and tested deployment.
  A representative physical task exercises the required primitives and verifies
  the requested object/result state; a narrower smoke test is labelled as such.
  Relevant failures or changed control code reopen affected requirements and
  the current passed/total display, preserving earlier results as history.
- [x] A person can use the website to run the integrated paper's method on
  physical YAM robots/arms. Record a verified physical execution of that method.
- [x] The actual physical arms are visible live on the website while the method
  runs, so a visitor can see that it is executing on real hardware.
- [ ] Immediately after a run finishes, the person can replay that just-completed
  physical YAM execution through the website, with retained footage showing the
  actual arms executing the integrated method.
- [x] The person can browse/select previous runs on the website and replay their
  retained physical arm footage, associated with the executed method and run.
  Mock animations do not satisfy either replay requirement.
- [ ] If the integrated method executes anything in simulation, those executions
  are reviewable within the integration website and tied to the corresponding
  run. A reviewer can inspect what ran and its results using suitable
  replay/visualization and relevant outputs, as appropriate to the simulation.
  Clearly label simulation content to distinguish it from physical-arm footage.
  If nothing executes in simulation, record an explicit not-applicable
  explanation instead of claiming simulation review.
- [ ] **Mandatory for every run:** first observed actual method-driven physical
  YAM motion occurs both within **15 seconds after the startup move to Home
  completes** and within **30 seconds after the Run/Start click excluding
  evidenced queue-admission waiting**, using the boundaries below (including a
  documented readiness timestamp when Home is unnecessary). Homing/preparation
  motion does not count. Record full elapsed times, queue entry/admission,
  excluded queue seconds and the queue-adjusted Run time for every run; a sampled
  demonstration is insufficient. Apply only the documented GPU-launch or
  research-grounded exceptions below.
- [ ] Every meaningful wait after a website action is immediately explained in
  a persistent inline status/progress area at that action (below Run in the run
  panel for launches). Show the current stage, a plain-language reason and real
  stage completion, with honest failure/stall status and available recovery.
  Verify the detailed wait-stage behavior below.
- [ ] Before marking the integration complete or reporting it done, open the
  deployed website and perform a final end-to-end physical YAM run through its
  normal user interface. Verify every completion requirement against that
  deployment and record evidence; unmet or unverified requirements block
  completion.

## Verify commands and numeric boundaries

Read [CONTROL-CONTRACT.md](CONTROL-CONTRACT.md) before physical runs and before
completion, including when an integration retains an older working checklist.
The installer distributes that contract independently of preserved evidence.
Its engineering gates are mandatory; they add no authorization/approval step.

Require actual command-path regression tests and pre-dispatch validation, exact
validated interpolation endpoints, strict rejection of invalid inputs, preserved
hardware safeguards and an actionable distinction between local input rejection
and physical safety stops. A test-only accepting mock cannot replace the real
deployed packet validator. Retain a failing packet and red-to-green reproduction
for every repair. Wire the tests into CI or the release preflight.

For advertised pick-and-place, verify the relevant approach/grasp/lift/transfer/
release/withdrawal sequence and fresh evidence of the object outcome. Passing
joint motion does not certify the untested sequence. Tie each claim to a task,
capability, source revision and evidence; invalidate affected current passes
after a relevant new failure. Installing this document is not test evidence.

## Model identifies the tested approach

Set the harness's **Model** field to the actual research approach/method being
tested. For example, a HarnessVLA run uses `HarnessVLA` as its Model value.
Resolve this value from the approach that actually executes and carry it
consistently through the website's model label/selection, run context and stored
run records, queue/email notifications, and replay/history attribution.

Record underlying foundation, planner or VLA model IDs and checkpoint names as
separate configuration metadata. Keep confirmed human runner identity and
execution mode in their own fields too.

Verify a run's Model value against the executed approach and retain evidence of
the website label, stored run record, notification and replay/history attribution.

## Verify normal UI execution

Site entry (`t_entry`), starting state and browser/session/network may be
recorded as optional diagnostic context. An agent can perform verification
through the normal UI.

Keep a timed screen recording showing the UI actions, the Run click,
startup Home completion (or no-Home readiness) and live physical arms beginning
the integrated method, linked to the matching run. Correlate recorded UI/physical
events with lifecycle logs on a common timeline; document any clock offset or
measurement uncertainty. Backend timing alone cannot verify physical onset.
Visual timing evidence may use retained accessible recording/verification links;
a local download is not required.

## Verify every Run and startup Home

For every run, record these fixed boundaries:

- `t_run`: the actual Run/Start click. Retain all subsequent wall-clock time,
  including queue waiting, preparation, coding, model loading and inference.
  Exclude only evidenced queue-admission waiting from the 30-second calculation
  below; do not restart the clock at admission, acknowledgement, dispatch, GPU
  readiness or a later status change.
- `t_home`: completion of that run's startup move to Home, using matched
  settled/ready completion for all participating arms, corroborated by live
  footage. Starting/submitting Home or reporting it accepted is insufficient.
  If no Home movement is necessary, record why and use the earliest documented
  per-run robot-ready confirmation after Run and normal queue/lease admission,
  before method preparation/execution. If already admitted and robot-ready at
  Run, use `t_home = t_run` with that readiness evidence. Readiness here concerns
  the robot, not GPU/model/code availability. Do not choose an arbitrary later
  event, repeat Home, or delay the readiness timestamp to reset this clock.
- `t_motion`: first observed actual physical arm motion executing the integrated
  method. Home and other preparation/parking motion do not count. An accepted or
  queued request, submitted packet, UI "running" status, inference start or
  backend-only timestamp is insufficient.

### Queue-admission wait in the 30-second budget

Record `t_queue` when this run's request actually enters the normal robot queue
and `t_admit` when that same request is first admitted/granted its robot
session/lease. Match queue/request and session/lease identifiers to the run and
retain actual lifecycle evidence. An accepted/queued submission is not admission.
Time between Start and queue entry still counts. Post-admission hardware
preparation, readiness checks, Home, coding, model loading/inference and other
setup still count; they must not be relabeled queue waiting. Later preparation
status changes or reacquisition cannot move the initial admission boundary.

Let `Q_run` be the duration of the evidenced queue-admission wait interval
`[t_queue, t_admit]` overlapping `[t_run, t_motion]`. Clip any queue waiting that
began before Start to `t_run`. If already admitted or there is no queue wait,
record `Q_run = 0` with matching admission/no-queue evidence. For a queued
request, missing entry or admission evidence makes the adjusted Run measure
unverified; do not assume zero or infer admission from Home, method readiness
or eventual motion.

Ordinary runs must satisfy **both** `t_motion - t_home <= 15 seconds` and
`t_motion - t_run - Q_run <= 30 seconds`. The queue exclusion is a normal part of
the 30-second budget, not a GPU or research exception; a full wall time over
30 seconds may still be a normal pass when the evidenced queue-adjusted time
meets its target. It does not change or pause the 15-second post-Home measure.

Retain full Run-to-motion and post-Home-to-motion times, excluded queue seconds
and queue-adjusted Run seconds even for failures and exceptions. Record every
run below (add rows), with visual evidence of Run and physical onset plus
matched Home/readiness and queue-admission evidence. Mark each target as pass,
missed target, unverified or exception. A normal pass requires the queue-adjusted
Run time and full post-Home time within their limits. Missing visual evidence or
an unmatched Home/readiness boundary leaves the affected timing unverified.

### GPU-launch exception

A run genuinely requiring new GPU launch/provisioning (for example on RunPod)
may claim an exception only for the evidenced time that launch blocks progress.
Show the **entire launch period** in persistent inline UI: actual launch start,
ongoing launch reason/stage and actual GPU-ready completion, with matching
provider/instance/job lifecycle evidence. If launch starts before Run, retain its
full start/ready interval and show its ongoing state when the run panel opens.
Warm/already available GPUs do not qualify. Record why a new GPU was necessary.

Keep the original clocks and full elapsed times. Record `t_gpu_start`,
`t_gpu_ready`, the full launch duration, and the evidenced GPU-launch blocking
seconds overlapping each measured interval (`B_run` and `B_home`). Only blocking
time inside both the actual launch interval and the relevant Run/Home-to-motion
interval can be excused; do not deduct concurrent time spent on unrelated work.
For the Run clock, also record `O_run`, the duration shared by the evidenced
queue-wait and GPU-blocking intervals inside `[t_run, t_motion]`. Exclude their
union, `Q_run + B_run - O_run`, never the overlapping seconds twice. For a GPU
exception, require `t_motion - t_run - Q_run - B_run + O_run <= 30 seconds` and
`t_motion - t_home - B_home <= 15 seconds`. Label a queue-adjusted Run target miss
or full post-Home target miss excused by GPU launch as **exception**, not normal
pass. Queue exclusion alone remains normal budget accounting. Keep raw queue and
GPU intervals, overlap, full timings and both adjusted calculations separately.
If GPU readiness precedes Home completion, `B_home = 0`: the full 15-second post-Home target still
applies. If Home completes during launch, only its evidenced remaining launch
blocking time can be excused; do not silently restart either clock at GPU ready.
Missing lifecycle or persistent UI evidence leaves the exception unverified.

Only the evidenced initial queue-admission interval is excluded from the
30-second budget; coding, model loading, inference, post-admission preparation
and other infrastructure delays outside actual GPU provisioning remain counted.
A warm GPU, a generic "loading" message or a slow model call is not a launch
exception.
Unrelated delays remain missed targets if they exceed the remaining limits.

Other exceptions require a specific justification grounded in the integrated
paper/research, explaining why it applies to that run and which target it affects,
plus a supporting source citation/link and relevant section/page. Slow coding,
loading, setup, post-admission delay or infrastructure delay is not in itself a
paper/research-grounded exemption; there is no permanent coding exemption.
Queue-admission waiting uses the normal exclusion above, not this mechanism.

| Run reference | Run/Start click (`t_run`) | Queue entry / admission (`t_queue` / `t_admit`), matching lifecycle evidence; or evidenced no-wait | Excluded queue seconds (`Q_run`) | Startup Home settled completion / no-Home readiness (`t_home`) and evidence | First observed method motion (`t_motion`) / visual evidence | Full Run-to-motion seconds | Queue-adjusted Run seconds | Full post-Home-to-motion seconds | Run / post-Home outcomes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| | | | | | | | | | |

- Exception record (repeat for each affected run):
- Exception category (GPU launch or paper/research-grounded):
- Affected run reference and timing target(s):
- Specific reason and why it applies to this run:
- GPU-launch evidence (if applicable: provider, instance/job reference,
  `t_gpu_start`, `t_gpu_ready`, full launch seconds, lifecycle log/link and
  persistent inline UI evidence covering the entire launch period):
- GPU-launch blocking evidence (`B_run`, `B_home`), queue/GPU shared seconds
  (`O_run`), excluded union (`Q_run + B_run - O_run`), both adjusted calculations
  and separate outcome for each target:
- Supporting paper/research source (for other exceptions: citation/link and
  relevant section/page):

## Visible progress while waiting

Use a compact persistent inline status area directly below Run in the existing
run panel; keep other meaningful waits beside their initiating control. Show the
current stage and why it is taking time immediately, keep it readable throughout
the wait, and visibly mark completed stages as actual lifecycle state advances.
A transient toast alone or a generic spinner is insufficient.

While actually awaiting queue admission, show `Waiting for robot admission` (or
clear equivalent), with the real queue reason/state and entry timestamp. Retain
its completed admission/grant state and timestamp, then show actual hardware
preparation/Home/model stages separately. Keep queue and GPU launch stages
distinct when concurrent; do not leave the queue stage pending after admission
or label all startup as queue waiting. Retain matching per-run lifecycle evidence
for the queue exclusion; no invented queue positions, times or completion.

When a model requires a new GPU, show only the stages that actually exist:
`Starting GPU` / "We're launching a GPU on RunPod for this model" -> `GPU ready`
-> `Loading model` -> `Running`. GPU startup must be explicit from its actual
launch start and throughout the launch period (immediately after Run when Run
initiates it); visibly confirm actual GPU readiness before subsequent
loading/running and retain completed-stage confirmation with start/ready
timestamps tied to lifecycle evidence. Use the applicable provider/model wording.
On failure or a stalled stage, state the known condition honestly and show an
available recovery action, such as retry or cancel where supported. Do not invent
percentages, ETA or completion, or expose irrelevant infrastructure internals.
UI transparency alone grants no exemption; only the documented GPU-launch
blocking interval qualifies under the exception above, with neither clock reset.

## Verify retained replays

Open the retained recording through the website, confirm actual playback and
appropriate seeking, and match it to the just-completed or selected historical
physical run. Record the matching run reference/link and observed verification
result. A link alone is insufficient.

This does not require pressing **Save video**, downloading/exporting video to the
agent's filesystem, making duplicate local copies or bundling videos in outputs.
Omit optional local downloads from routine acceptance work; they are not a
completion requirement and must not create an approval or needs-input blocker.
Download locally only when explicitly requested or concretely necessary for the
task. Required tool/platform permissions still apply; do not bypass or retry a
denial through another route. Website/backend recording capture and retention
remain required.

## Final verification before completion

Open the deployed website and its associated source repository. Use the normal
website controls to join, run the integrated method on physical YAMs and watch the
actual arms live. First verify the required command-contract CI/release checks;
choose a representative task covering the advertised primitives and verify its
actual result. Reconcile later failures and changed control code with current
acceptance status instead of carrying forward a stale smoke-test pass.
Check the unchanged 15-second post-Home measure and the
30-second Run/Start-to-motion budget excluding evidenced queue-admission wait.
Keep fixed boundaries, full elapsed times, queue entry/admission/excluded seconds
and queue-adjusted time; verify any GPU-launch exception uses the queue/GPU
union without double subtraction. Check actual queue-to-admitted-to-preparation
inline stages; site entry is optional context. Check approach/runner identities,
replay of the just-completed run and selection/replay of previous runs. Review
every checklist item against current evidence, including public visibility and
actual user attribution in policy/model tests, with execution mode separate.
Check the website, repository and each demo artifact type as a logged-out visitor;
record working public links or the explicit user-directed visibility exception.
Verify that Model identifies the executed approach consistently in the website,
run records, notifications and replay/history, with underlying model/checkpoint
configuration recorded separately.
Verify that the selected underlying models match the researcher's choice or
explicit delegation, that run details show what actually executed, and that any
replacement or comparison is labelled accurately.
Verify wait status appears immediately, keeps a readable reason, and visibly
confirms real stage completion (GPU ready before subsequent loading/running).
Check failure/stall status and available recovery evidence too. Record the
tested deployment, run and evidence below.
Leave unmet or unverified items unchecked and report gaps and explicit exceptions
before any completion claim.

## Integration and evidence

- Paper / method (link and version):
- Model-choice evidence (question/response or prior explicit choice/delegation,
  reference, per-role preferences and constraints; or no-model explanation):
- Selected model configuration (roles, providers, exact model IDs/versions or
  checkpoint revisions, inference settings, editable configuration location and
  original-paper baseline versus replacement/comparison variants):
- Model verification and run provenance (current availability/capability and
  compatibility checks, official sources/check date, run references, requested
  versus actually resolved identifiers, unresolved aliases and website evidence):
- Final verification (reviewer/date, tested website URL and deployed revision,
  physical run reference):
- Final checklist review (evidence for every item, replay links/timings, unmet
  items and explicit exceptions):
- Command-contract evidence (advertised primitives/arms, units/frames/ranges,
  actual packet generator/serializer/validator revisions, required CI/preflight
  command/result and endpoint/interior/invalid-input/zero-dispatch coverage):
- Failure regressions (sanitized packet/starting state, dispatch classification,
  red-to-green proof, unchanged safety checks and deployed repair revision):
- Representative task acceptance (capability/task, approach/grasp/lift/transfer/
  release/withdrawal where applicable, fresh verified outcome, exclusions and
  current requirements reopened by later failures or changed control code):
- Actual approach name / website label evidence:
- Model-as-approach evidence (executed approach, website Model value, stored run
  record, queue/email notification and replay/history attribution; separate
  underlying model/checkpoint configuration):
- Human join evidence (name/email collection or confirmation, prefilled defaults
  and edits to both fields):
- Run context evidence (run ID, approach and runner identity; website attribution):
- User-initiated test evidence (run ID, confirmed human runner, actual approach,
  separate execution mode; editable defaults and missing-name confirmation):
- Unattended/system activity evidence (explicit system identity, execution mode
  and actual approach; no fabricated person):
- Wait-status evidence (action/run reference, immediate inline visibility,
  ongoing stage/reason and real completion transitions):
- GPU-startup UI evidence (startup shown after Run, actual readiness confirmed
  before loading/running, completed stages and matching lifecycle evidence):
- Failure/stall status and available recovery evidence:
- Website URL:
- Website source repository URL / deployed revision:
- Public-default evidence (logged-out access checks and links for website,
  repository, runs/results, live demos, recordings, replay/history, simulation
  outputs and supporting demo evidence; explain any artifact type not produced):
- User-directed visibility exceptions (write "none", or affected materials/scope,
  current visibility, explicit user instruction/change, date and reference):
- Physical-test authorization/scope (source path/heading or commit URL, website
  and queue/run backend origins, station/arms, confirmed runner identity fields,
  method/task, duration, expected motion and recording/replay destination):
- Approval-context evidence (surfaced notice and escalation wording, applicable
  user invocation/selecting instruction and harness contract version/scope,
  review decision/rationale if required; redact private email from public evidence):
- Physical execution (date, method/configuration, YAM station/arm IDs, run ID):
- Live physical arm footage (website location and evidence link):
- Just-completed replay URL / matching run reference / immediate availability
  and observed playback/seeking result:
- Previous-run browser URL / selected prior run reference / replay link and
  observed playback/seeking result:
- Simulation review (corresponding run reference, website review link, what ran
  and its results, suitable replay/visualization/outputs, clear simulation label;
  or explicit not-applicable explanation if nothing executes in simulation):
- Per-run timing verification (tester/date, browser/session/network and robot
  readiness; evidence for every run in the timing table above):
- Optional diagnostic context (site entry `t_entry`, starting state and
  browser/session/network):
- `t_run` / `t_home` / `t_motion`, full Run-to-motion and post-Home-to-motion
  seconds, queue-adjusted Run seconds and separate target outcomes:
- Queue evidence (`t_queue` / `t_admit`, matched run/request/session/lease IDs,
  lifecycle links and persistent inline stages), excluded `Q_run` seconds; or
  evidenced already-admitted/no-wait with zero exclusion:
- Matched settled Home completion evidence for participating arms, or no-Home
  reason and earliest robot-ready timestamp/evidence (already ready: Run time):
- GPU launch start/ready/full interval and inline UI/lifecycle evidence, `B_run`
  / `B_home`, queue/GPU overlap `O_run`, excluded union, adjusted calculations and
  exception outcome if applicable (otherwise "none"):
- Timed screen recording / matching physical run evidence and clock correlation:
- Remaining gaps:



## Current one-minute capture result — 2026-11-04

The user accepted the minute simulation and explicitly requested integrating this
motion with the playground and obtaining its video. That invocation resumes the
requested work after the prior pause; no additional physical permission was
requested. Model choice remains not applicable: deterministic calibrated IK.
No visibility exception was requested. Public source is the existing
[scene-video draft](https://github.com/andlyu/blupe-remote-bots/pull/283).

The current local deployment is http://127.0.0.1:8797/ using `minute.py serve`.
Its Run dialog prefilled the actual confirmed name/email; both fields were
editable. The normal UI Run at21:17:21.709UTC submitted the named minute method
with a120-second maximum session, preserving queue/Home/lease/validation/Stop.
Private email remained operational only. The exact launch preflight passed25
regressions and the600-frame simulation before physical access. Current source,
calibration and canonical runtime/controller hashes are retained in
[evidence/minute-launch-preflight.json](evidence/minute-launch-preflight.json).

Both actual gateway packets accepted and all600points completed with settled
feedback in one physical run. No uncertain or timed-out movement retry occurred.
The planned60-second path took73.81seconds of reported physical execution with
settling. The84.6-second full recording retains real setup/packet timing, both
wrist views and the top camera:844samples,2991images,812aligned training-valid
rows,zero captureerrors and one missed tick. Export retains two missing-image
ticks and labelled held frames. Normal parking and torque-off were verified.

- [Physical scene movie](https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/videos/ep_47151c9fe197419d.mp4)
- [Capture/progress/timing evidence](evidence/minute-physical.json)
- [Movie metadata](evidence/minute-video.json)
- [Decoded seeking](evidence/minute-playback.json)
- [Dataset publication and normal history playback](evidence/minute-publication.json)
- [Motion design and simulation](ONE-MINUTE-SIMULATION.md)

Dataset commit554a4f99e057d1cf5b198edb797cfaab56ef8302 contains the full movie and
honest capture receipt; the source samples hash matches the finalized USB
recording. No full training archive publication is claimed. The separate normal
four-camera preview is10×. The full movie was selected from normal run history
and observed playing at1× with duration84.6s/readyState4, named method and actual
runner. All846frames decode; seeks at1,20,45,75seconds pass. No assessment vote,
email notification or result relabeling was submitted by this task.

The first reported physical progress was4.66seconds after matched Home completion.
Live UI screenshot observations bound actual onset by11.63seconds after Home and
24.31seconds after Run. Queue join/admission and original Run times are retained.
A continuous timed UI screen recording was not retained, so strict harness timing
certification remains unchecked rather than inferred from backend events alone.

| Current requirement | Evidence / remaining limitation |
| --- | --- |
| Public website and exact source deployment | Existing public viewer/history and public source; this specific launch page is local, not publicly deployed |
| All demo materials public | Physical full movie/preview public; source/simulation publication retained in draft branch; no public launch-page deployment claim |
| Actual method, confirmed human and editable defaults | Verified normal Run setup and replay/history |
| Model selection | Not applicable; no learned model or GPU |
| Command-contract/release gate |25passed; exact generator, two serializers, fractional holds, invalid zero-dispatch, chunk join/cursors, collision snapshot and launch hash gates |
| Representative scene capture |600actual waypoints, changing camera views, saved full-speed movie; reconstruction quality is not advertised or certified |
| Runnable method and live physical visibility | Verified current local deployment through normal UI, actual live arms observed |
| Immediate replay | Processing stage shown; quick replay saved, but immediate post-finish playback timing was not fully measured |
| Historical selection/full playback | Verified normal library selection and full84.6s movie playback |
| Simulation review on website | Embedded labelled minute simulation; chat preview reviewed, in-site playback/seek not separately certified |
|15s/30s onset | Observations meet bounds above; continuous UI recording requirement remains unverified |
| Persistent wait/failure stages | Queue/readiness and replay-processing messages observed; full checklist-wide lifecycle/recovery audit incomplete |
| Final end-to-end | Current local UI physical run and history playback verified; public deployment and remaining broad certification stay open |

Status: **capture task executed and video delivered; full integration checklist
incomplete**. No explicit exception removes the unchecked requirements.

## Historical initial 12-second verification record — 2026-11-04

Status: **incomplete**. The physical capture executed; retained full dataset video,
publication, complete normal-UI acceptance and strict timing remain open. Do not
interpret the three checked documentary items as full integration acceptance.

Invocation: user requested a 3D-scene video on the YAMs through this harness,
forward arm travel with cameras aimed at the scene, saving to the existing
dataset, and simulation verification **before** connecting the physical playground.
The contract above and `BLUPE-HARNESS-CONTRACT.md` apply. No visibility exception.
No foundation/policy model dependency: this is deterministic, calibrated IK.
No model calls, GPU launch, model selection or research timing exception applies.

- Method: **Forward scene video · 12 cm / 12 seconds**. Fixed +0.12 m per-arm
  base X, 120 points at 10 Hz, measured wrist attitude and gripper fractions held.
  No manipulation/pick/place or reconstructed 3D model is advertised.
- Website: shared public viewer https://playground.blupe.io/ and configured local
  run UI http://127.0.0.1:8796/ . Source repository:
  https://github.com/andlyu/blupe-remote-bots . New integration source is local
  and not yet published; no deployed revision is claimed for it.
- Runner: actual confirmed Andrew Lyubovsky. Name/email were editable in normal
  Run setup and filled from prior confirmed identity. Private email was submitted
  only to the existing operational backend, and is omitted from public evidence.
  Execution mode `agent-operated` remains separate from method and identity.
- Backend: https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com .
  Station `yam-1`, both arms; maximum admitted session 60 s. Scope was rendered
  with tools/blupe_harness.py before the run; private operational scope remains
  outside source at /private/tmp/yam-scene-video-01a1a7cc/scope.json.
- Coherent shared runtime: git archive of
  `7ba2427ba960ad30af99c8fedd05c5196685295a`; original dirty checkout was preserved.
  Simulation source, canonical validator hash, calibration ID, MuJoCo version,
  held endpoint fractions, invalid zero-dispatch cases, physical guard samples,
  video hash/playback/seek and command runtime are recorded in
  [simulation verification](evidence/simulation.json).
  Initial simulation passed before any physical API access. After the completion
  repair, offline simulation was rerun at 20:24 UTC and passed in 3.225 s.
- Physical episode: `ep_11d0dcff60b448ba`, session
  `sess_3d5da0ff2ba4499a`, trajectory `traj_ep_11d0dcff60b448ba_0`.
  One normal UI Run, no movement retry. Existing gateway accepted its packet;
  all 120 executions were reported before settled final feedback. The UI ended
  with an erroneous local completion-validation failure; historical status is
  preserved rather than relabelled successful.
- Final-check repair: Home is required only before initial dispatch; completion
  uses next cursor `last_step+1` and the runner's existing 0.05 rad endpoint
  tolerance. Fresh safe/settled matching feedback, same episode/lease, bounds,
  command pacing and physical gateway checks remain required. Regression was
  red (1 failed / 6 passed), then green (7 passed in 0.45 s). See
  [repair record](evidence/completion-repair.json).
  No new physical run of the repaired code is claimed.
- Raw recording: finalized and durable on Jetson USB at
  `/home/andrew/maxone-offload/yam-training-direct/ep_11d0dcff60b448ba`;
  139 sample rows, 496 images, 60 capture errors, 0 training-valid aligned rows.
  Samples SHA256 `6ac6ad2649c2d1755461cd6ca7bafea14a1f5b2acc621d779741baab15b59d61`.
  Raw footage is retained, but this does not establish complete synchronized
  three-camera video or training quality.
- Measured feedback with canonical native FK predicts 0.1152 / 0.1162 m forward
  travel. This is a model-based estimate, not independently surveyed accuracy.
  [Measured result](evidence/measured-sweep.json).
- Quick replay: [exact physical episode](https://playground.blupe.io/api/quick-replays/ep_11d0dcff60b448ba/745afeac3352b49433507d4dfdbb7a2ed44efa36277607af36c81940c3f63c5f.mp4).
  It is **observer-only**, 10× speed, 1.733 s; it cannot substitute for the
  requested full wrist-camera video. Media loaded to readyState 4 and ended in
  the normal replay dialog, but explicit play/seek verification was interrupted.
  Public metadata at 20:23 UTC still reports original_available=false and
  missing method/runner attribution. HF publication is not verified.
- At 20:26 UTC the existing preview uploader is active (PID 937208), waiting
  for its unchanged video gate: live top/observer, held left/right; 7.99 fps,
  fresh health, ~2329 MiB available. Do not disable the gate. `preview-export`
  now exists, but no ready/upload receipt was present. This is a live service
  wait with an identified condition, not a completed upload.
- Normal parking/release verified: DISABLED, both arms parked at joint zero,
  torque-disabled, no active session; auto queue enabled and idle. At 20:24 UTC
  the local run UI was restored after its prior process handle was confirmed
  missing. Its live cameras play with ~2 s delay; no new Run was submitted.

### Item-by-item acceptance audit

| Requirement | Current authoritative result |
| --- | --- |
| Website + associated published source/revision | Local UI works; new source not published; public integration deployment unverified |
| All demo materials public | Public quick replay only; source/sim/full dataset movie remain open |
| Actual approach named | Passed in configured UI and original run configuration |
| Underlying models chosen / no-model explanation | Passed: deterministic IK; no model dependency |
| Editable confirmed identity/defaults | Actual fields editable and confirmed; automatic known-default prefill not fully verified |
| Method + human identity in context | Local interactions retain both; public replay currently lacks attribution |
| Human identity for person-initiated tests | Passed: Andrew Lyubovsky; mode/method separate |
| Offline command contract and release preflight | Generator/real serializer/validator + guards passed; completion regression passed; CI/release procedure still needs documentation/wiring |
| Representative task acceptance | 120 points executed; raw captures have gaps; full wrist footage and repaired-code deployment not certified |
| Physical method runnable | Historical normal-UI physical run exists; repaired-code final UI verification open |
| Live actual arms visible | Actual live frames observed; no retained timed UI recording of onset |
| Immediate just-completed replay | Observer quick clip exists; full footage/play/seek verification open |
| Historical run selection/replay | Not verified for this integration |
| Simulation review on website | Local labelled video exists/loads; full browser playback and public review not verified |
| Per-run 15s/30s timing | Original UI click 18:31:48.980 UTC; queue join 18:31:50.239; Home completion 18:33:07.450; first packet accepted 18:33:09.961. These backend events are not visual motion proof. Admission boundary and timed UI recording absent; both strict timing measures UNVERIFIED, no exception |
| Persistent wait/failure explanations | Queue/readiness and completion error shown inline; full lifecycle-stage retention/recovery not certified |
| Final deployed normal-UI end-to-end run | Unmet; no completed current-version/public-deployment acceptance claim |

Remaining work: publish/verify the full saved wrist-camera scene movie through
normal dataset pipeline; play/seek and exact-run historical selection; repair
public attribution; publish source/simulation evidence; wire release preflight;
verify the final deployment and strict UI/physical timing. Keep all affected
boxes open until corresponding current evidence exists.

2026-11-04 source-package update: the full `run.py verify` gate now executes the seven completion regressions and the simulation/serializer/guard/video checks together. Inputs include exact public runner/controller revision hashes. A dedicated GitHub Actions workflow is prepared; its remote CI result remains unverified until published/executed. Local completion regressions passed7/7 in0.39s; exact-controller simulation passed in2.931s. Captured source/API diagnostic shows stale source roles plus incomplete RGBD transfers; API-only JPEG success did not establish healthy sustained capture. Sanitized evidence is in docs/evidence.

Public source: [draft PR283](https://github.com/andlyu/blupe-remote-bots/pull/283), commit `b872495242254b43dee73be33b887c45afe97afd`. No default-branch merge or public integration deployment is claimed. Camera recovery restarted only yam-playground-cameras.service after idle/empty-queue/torque-off and calibration identity checks: PID2169→2042012; source fresh ages23/39/58ms and all4HD views live at8fps after recovery. The normal uploader resumed backlog processing. A240s bounded task supervisor (unit yam-scene-video-upload-01a1a7cc.service,PID2044383) now selects only this saved episode through unchanged normal eligibility/readiness/video/resource/session gates. Its ExecStopPost restores the normal backlog service. This is not a new arm run.


### Latest scope and evidence — one-minute iteration

The user clarified the priority is a straightforward scene video and requested
exactly one minute of trajectory, farther forward reach, and camera aim toward
the shared center and other scene regions. The native goal was paused before
this explicitly requested simulation iteration. No revised physical run occurred.

The new offline-only `viewpoint_sim.py` passes600 points/60 seconds at10Hz,
two real serialized packets, and1076 controller snapshot swept samples.
Maximum joint change0.02859rad per100ms stays below0.035rad. Camera position
ranges are about21cm forward,16cm sideways and11cm vertically. The rendered
60.000-second video has600 decoded frames and verified seeks. Representative
left/right views were visually inspected. See
[minute trajectory](ONE-MINUTE-SIMULATION.md),
[verification](evidence/one-minute-simulation.json) and
[comparison](evidence/one-minute-comparison.json).
Projected synthetic-grid coverage improved from75%/62% to100%/100%; projection
ignores occlusion and does not certify actual physical coverage/reconstruction.
Rejected IK/pacing candidates were never dispatched; hardware limits unchanged.

The earlier physical run now has a full-speed20.3s movie published at
https://huggingface.co/datasets/andlyu/Public-YAM-runs/resolve/main/videos/ep_11d0dcff60b448ba.mp4
in commit e75888ae02406fbc9be0efeae469cc0d5d3cfe35, with an honest capture receipt.
It includes left/top/right and retains held/missing-frame labels. Browser history
selection and playback were observed with the actual approach and confirmed
human name; decoded seeking passes, but explicit browser seek was interrupted.
This corrects the earlier pending-publication notes. The failed targeted uploader
never processed data; normal uploader restoration succeeded. Actual original
name/configuration were projected to the public attribution DB without email
or changes to outcome. The normal four-camera preview uploaded in c63b9006.
The public quick-replay API still reports model=null/original_available=false;
the normal browser library nevertheless displays the named method and plays
the full dataset movie. API reconciliation is not claimed.

The existing draft source package has green Shared runner, RoboHarness command
contract and Forward scene video preflight checks at b8724952 (Actions runs
41908344366,41908344323,41908344316). This minute-long local revision is not yet
published or wired into that CI. It does not inherit physical acceptance.

Current acceptance remains INCOMPLETE. The new full-minute physical capture,
clean camera continuity, current-version deployed Run path and visual onset
measurements remain unchecked. No timing exception or complete integration
claim is made. The existing live launcher is the old12-second method; simulation
results cannot cause automatic physical movement.
