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

- [x] A usable website exists, with an associated repository containing the
  website's source code. Record both links and the deployed source revision.
- [ ] Everything in the playground demo is public by default, including the
  website, source repository, runs/results, live demos, recordings, replays/history,
  simulation outputs and supporting evidence. Any nonpublic exception reflects
  an explicit user instruction or visibility change, recorded below.
- [ ] The website clearly names the actual approach/method being run. Use the
  executed method's name; Spotter is an example, not a shared hardcoded label.
  The **Model** field identifies the approach being tested, as specified below.
- [ ] The researcher was asked which underlying models/versions to use before
  model-dependent work, or their prior explicit choice/delegation was retained.
  Choices include newer/custom models; current availability and compatibility
  were checked. Configuration and run details retain the selected and actually
  resolved models/settings, with baseline/replacement variants labelled and no
  silent fallback. Record evidence below, or a justified no-model explanation.
- [ ] When a human joins, collect or confirm their name and email. Prefill known
  identity/default values where available and let the runner edit both fields
  before joining.
- [ ] Run context includes the actual approach and confirmed runner identity;
  the website makes clear which method is running and whose run it is.
- [ ] Policy/model tests initiated by a person retain that actual user's
  confirmed name as runner. Use available identity and editable name/email
  defaults; require the real name to be provided/confirmed if missing before
  testing or running. Do not substitute `Anonymous`, `Autonomous` or `Automated`
  for that person. Record execution mode (such as `automated test`) and actual
  approach separately from human identity. Genuinely unattended/system activity
  has an explicit system identity; never fabricate a person's name or email.
- [ ] Every advertised control primitive passes the offline command-contract
  gate through the actual parser/generator/serializer and canonical validator,
  including measured fractional starts, numeric endpoints, invalid-input and
  zero-dispatch failure tests. A required CI/release-preflight result and exact
  source/dependency revisions are retained. Follow [the control contract](CONTROL-CONTRACT.md).
- [ ] Task acceptance matches the advertised capability and tested deployment.
  A representative physical task exercises the required primitives and verifies
  the requested object/result state; a narrower smoke test is labelled as such.
  Relevant failures or changed control code reopen affected requirements and
  the current passed/total display, preserving earlier results as history.
- [ ] A person can use the website to run the integrated paper's method on
  physical YAM robots/arms. Record a verified physical execution of that method.
- [ ] The actual physical arms are visible live on the website while the method
  runs, so a visitor can see that it is executing on real hardware.
- [ ] Immediately after a run finishes, the person can replay that just-completed
  physical YAM execution through the website, with retained footage showing the
  actual arms executing the integrated method.
- [ ] The person can browse/select previous runs on the website and replay their
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



## Working evidence — November17,2026

User invocation: create a separate Gemini version of BluPe with a hosted worker.
The user selected the current BluPe layout with simulation/results added and the
title Gemini, and asked not to be questioned about a description. Underlying
planning/coding/vision model choice is Gemini4Hydrogen from the identified Google
release. Exact configured ID: `gemini-4-hydrogen`; provider alias resolution and
actual inference remain unverified. No model substitution is authorized.

Source worktree is isolated on `codex/gemini-blupe`. Sites project is
`appgprj_6afd3a1c711481919a08a0d1a631e7a2`; expected site origin
https://gemini-blupe.andlyu.chatgpt.site is not yet proof of deployment.

Implemented: preserved-layout frontend, public camera gateway, persistent worker
run store, owner-bound Run/Stop, request idempotence, private email separation,
SDK0.1.23 model/skills/workspace configuration and retained simulation-artifact
routes. Six real store/ASGI regressions pass. Gateway/browser scripts parse and
unconfigured Run correctly returns503. Those checks are not the physical
command-contract gate and do not establish simulation or hardware readiness.

Official plugin checkout9cb7f624 and MuJoCo Playgroundc9de052f are pinned in
isolated temporary runtime checkouts. SDK import passed. Simulation CPU
dependencies are currently installing. No model call or robot session has run.

Physical adapter, YAM1 scene matching, actual generated-controller simulation,
model entitlement/latency, public source/site checks, real task, onset timings,
identity defaults, immediate/historical replay and all other unchecked acceptance
requirements remain open. Physical Run is temporarily unavailable rather than
routed to a different method. The intended final scope remains unchanged.

## Progress — November18,2026 UTC

Public site https://gemini-blupe.andlyu.chatgpt.site deployed version1 at Sites
source722dd952cdf1234ee2c9cb3a136b6bc1cb079fca; logged-out homepage and state200.
Public integration source branch codex/gemini-blupe at19ce5192. No private contact
fields or credentials are in these public sources.

Selected Hydrogen API transport passed5.839s using SDK0.1.23 with no tools,
synthetic text only and confirmed Andrew Lyubovsky attribution. This does not
verify controller generation or vision. Official single-arm simulation rendered
20frames over2simseconds,5.303s wall. It does not establish YAM1 scene matching.

Eight real Store/HTTP regressions pass, including Stop winning over late
completion. Custom SDK tools and keyless network-disabled rootless execution
are implemented; hosted image build and actual isolation qualification are in
progress. A separate account/resource slice on the inspected existing worker
avoids new compute provisioning. No physical session has been submitted.
All unchecked final acceptance requirements remain open.

November18 follow-up: version2 source1e492d6e7cdfbd93ca63c4d527053fb51f3a8a48 is public and connected to the actual Python worker. Browser verification shows editable known identity defaults and honest pending simulation/physical status. Cloudflare rejects redirect:error before network dispatch; camera regression reproduces503 and passes200 after manual-mode repair. Direct canonical JPEG probes pass, while RGB-D transfers have failures; no camera/robot services were changed. Hosted isolation verification remains unfinished: cold rootless image preparation exceeded45s, then the reference scene exposed a missing ALOHA asset. Rebuilt both exact pinned assets; qualification is pending. Real API-key transfer was rejected by automatic approval review and remains unperformed while explicit approval is requested. No physical session or model-backed hosted task has run.

Runtime qualification now passes: image5ad3bffb35b8d926dd0f83c86f9f90b378d64ed55df842330b71ea76edd7518e, eight real isolation checks,18renderedframes/1.8simseconds,36.617s in-container and40.164s executor wall. Public supporting evidence is in evidence/runtime; the hold controller is handwritten, not generated. Site version3 camera repair is publishing. Model API-key installation awaits explicit approval following automatic review rejection. Physical acceptance remains unverified.

Website evidence: https://gemini-blupe.andlyu.chatgpt.site, public Sites version4/source172689646798353fb32d751992c4c3ad615e7988; canonical source4e3c6c2d; API58e4922a. Actual browser shows current overhead and both wrist views, preserved layout, working tabs, editable known identity and honest pending model/physical stages. Screenshot evidence/runtime/site.jpg excludes private contacts. Only the website-existence requirement is checked; every remaining unverified requirement stays open, including full generated-controller workflow, actual YAM1 method run, command contract, matched scene, representative outcome, startup timing and retained physical replay. No visibility exceptions were requested. The active goal is not complete.

November18 continuation: explicit user approval received and existing key installed privately on the specified worker. Release5f05a9c1 submitted actual testaf6e3759-c012-4452-b910-7ff329548cf5 as Andrew Lyubovsky, execution mode automated test, Model Gemini Robotics, underlying Hydrogen. Google rejected first inference with HTTP402/prepaid credits depleted before controller/tool execution. No simulation or physical session resulted. Billing must be restored; no new spend inferred. Retained provider evidence and required15-test offline preflight are in evidence/runtime. Joint/gripper compiler now passes real canonical client serialization after a3-endpoint float wire-conversion repair; full physical command/control/scene matching gate remains open. See docs/COMMAND-CONTRACT.md.


## Current engineering checkpoint — 2026-11-18 08:20 UTC

Public site remains Sites version4 and production API sourcee075e8d3. The user-approved key is installed; Google prepaid credits remain depleted. No funding reply, replacement model/account or spending was inferred and no new model call was attempted. No physical queue session or robot command has occurred.

Added installed-variant bimanual geometry with16qpos, native limits/zero additional offsets, articulated coupled fingers and three provisional pinhole camera transforms. Exact upstream XML verification exposed a different mount/TCP from the captured installed XML; the installed variant and public matching meshes are retained with MIT provenance. Forty deterministic pose samples agree with canonical FK. Google generic IK runs on the same model and achieved residuals are independently checked.

Actual offline rootless scene rollout:60frames/6simseconds,87.544s in-container/89.032s executor wall, no MuJoCo numerical warnings, all three rendered views. Camera K round-trip maximum1.9311e-5pixel. The controller is handwritten, no object/contact success is claimed, dynamics/collision qualification remains open. Supporting video/traces/receipt are in evidence/yam1-engineering.

The generated-controller host bridge now composes with real RunnerController/serializer in offline tests, preserving queue/lease/Home/feedback/Stop ownership. Actual rootless stdio completion also passed against a zero-network serializer spy; cancellation/oversized-output qualification is being retained separately. The API key/capability/private contacts are absent from this container interface. The new adapter is source-only until full deployment/state/capture/contact qualification. All current unchecked checklist items remain open; the final scope is unchanged.

Final source-bound channel matrix passes normal/cancel/oversized:2/0/0packets, exact close/open endpoints, all named containers removed. Evidence/controller-channel retains code hashes and timings. Canonical required preflight passes28tests(test0.381s, gate1.4041s) plus gateway and inline JS; removing the geometry/IK test module fails release preflight(exit1). Harness adoption check is current/preserved. Checklist remains1/17 checked; no new physical/model readiness claim.

## Common runtime source checkpoint — November18,2026

Production remains APIe075e8d3/Sites4 while the new bimanual common-controller
release is prepared. The user-approved key remains installed; billing is
unchanged/unavailable. Actual handwritten runtime image65f9521a passed ten
isolation/runtime checks and43frames/4.3simseconds (37.528s executor wall).
Forty required offline tests/gateway/JS pass; removing station-input coverage
fails release. Evidence/common-runtime retains the first failing response,
red/green mapping regression and repaired rollout/report/source hashes.

Read-only live input collection rejects stale source joints before model calls.
YAM1 mesh peer is offline; cached joints last observed07:28:40UTC are not current
robot/support/torque evidence. No queue entry, robot command or email occurred.
Existing host SSH is currently unreachable while public API remains healthy;
no firewall changes were made. Site freshness labels are prepared separately.

Only website existence is verified. Model-generated YAM1 task, matched task
scene/contact, production physical composition, native Cartesian/contact checks,
representative manipulation, timing and retained physical replay remain open.
No checkboxes changed and full objective is unchanged.

## Public website checkpoint — 2026-11-18 16:08 UTC

Existing public Gemini Site version6 deployed successfully, source
4e31dd1ee58e1c2f3e20dd1743472b42aa2403c0, at
https://gemini-blupe.andlyu.chatgpt.site . Actual browser confirms retained BluPe
layout, simulation/results panel, editable identity defaults, disabled Run/Simulate
when unavailable, preserved failed-run history and working camera view switching.
Offline camera empty states no longer show broken-image icons or retry flicker.
Cropped screenshot evidence/common-runtime/site-v6.png excludes private contacts.
No current physical or model success is implied by the screenshot.

Production API remains e075e8d3; the new source-bound worker archive is prepared,
not deployed. Existing SSH access is unreachable, and temporary current-network
access approval is pending. Approved key remains installed; Google funding and
station connectivity remain pending. All previously unchecked acceptance items
are still unchecked (1/17 checked); no model/robot request or email was sent.

## Controller handoff source checkpoint — November18,2026

Actual old run_agent accepted a controller edited after its simulation. The
scripted SDK/engine regression reproduces this (baseline23a1aac5,exit1); current
source retains original controller/station and all attempt artifacts outside
the generated mount, binds report/source hashes, preserves identical-source
evidence and restores host scene inputs on resimulation. Cleanup uncertainty
cannot qualify/restart that execution. Required preflight now passes51tests plus gateway/JS. Removing or skipping
required binding coverage fails release. Authenticated artifact history and
per-attempt replay UI are prepared for publication.

Local UI fixture played the prior handwritten4.3s engineering replay and showed
current/older attempt links. This is not a new real model or physical run. New
host executor still needs actual Podman qualification after SSH returns; all
eight source files in the previously qualified runtime image remain unchanged.
Production API stays e075e8d3; no key transfer, model retry, spending, queue entry,
robot command or email. Full task-scene, model and physical acceptance remain
unchecked; checklist1/17. See docs/CONTROLLER-HANDOFF.md.

Publication checkpoint21:15UTC: public Site7/sourcebcb436df2455765665ad3c51b7a8ee10bc97a2b2
deployed successfully. Actual published history selection shows original failed
provider-credit events and disabled actions; cropped proof/site receipt are in
evidence/controller-handoff. New host source8ae29dd4/archive remains prepared,
not deployed. Canonical51-test preflight passes; no checkboxes changed. Current
provider state remains credits depleted; no funding, SSH-access or station reply.
No further model call, spending, key transfer, queue entry, robot action or email.

## No-email queue prerequisite — November18,2026

Live contracts and deployed image audit show queue-arrival emails are enabled
and independent of email_run_video. No physical queue request has been made.
Prepared dedicated no-email API endpoint preserves normal admission/auth/default
notifications and fault alerts. The existing image rejects this endpoint before
queue/mail; the patched image passes7offline ASGI/Mock-publisher checks. The
Gemini client retains actual human attribution through the canonical serializer
and has no email-endpoint fallback across unsupported versions, rollback or
ambiguous POST outcomes. Five client/transport-spy checks pass.

No new model, robot, identity submission or real email occurred. Backend extension
and worker are not activated yet; physical orchestration and all previously
unverified acceptance remain open. No checkbox changed; full objective unchanged.

## No-email API activation — 2026-11-18 22:44UTC

Existing Session API deployment60 is ACTIVE, image62/digestacb46843a957a10fa7c1eb2c21d23a67b564fe3073d0058d652bc02a53343b66. Read-only public contracts match all21 tested schemas; private environment/command/ports and public endpoint/health-check compare unchanged to deployment59 except image. YAM1 calibration remains9773d518; connected Robo-house recovered DISABLED. YAM1 has no connected station. Source495fd611 introduced the no-email canonical queue client; required56-test packaging gate passes. No identity/queue POST, real email, model retry or robot command occurred. See docs/NO-EMAIL-QUEUE.md and evidence/no-email-queue/production-api.json.

Site7 remains published; a fresh browser reload rendered Gemini, camera tabs, prompt/library and disabled Run/Simulate. A Python HTTP probe received403 and is retained accurately rather than counted as browser failure/success. The new worker is packaged, not deployed (production e075e8d3). Google credits, worker SSH access and station connectivity remain unresolved. Physical orchestration, matched task-scene/contact, generated-model task, onset and physical replay are still open. Checklist remains1/17; full objective unchanged.

## Canonical physical lifecycle source — 2026-11-18 23:04UTC

Prepared PhysicalRun now owns the canonical preparation/controller/capture
threads without resetting the original website Start. Retained simulation source
is staged separately and rebound at actual process launch; no restart after
uncertainty. Native Stop precedes channel close. Existing camera recorder accepts
Gemini Robotics attribution and preserves it through capture/publish/recovery;
RoboHarness defaults remain covered. Required72offline tests and separate full
10-case recorder suite pass, using mock station/synthetic frames/real encoding.
See docs/PHYSICAL-LIFECYCLE.md for exact evidence and unfinished composition.

The package includes canonical runtime/staging assets/dependencies, but no new
host deployment or robot route activation occurred. Google credits, SSH access
and YAM1 source remain unresolved. No model/queue/identity/email/motor request.
Full worker/store/Stop-watcher/gateway/physical replay composition, task-scene and
actual model/physical/timing/final-UI acceptance remain open; checklist1/17.

## Current completion audit — 2026-11-19 01:20UTC

Public Site8/source d12b741ae79dd092d3729a89391e0a4c028c0b93 is deployed at
https://gemini-blupe.andlyu.chatgpt.site (deployment appgdep_6afe4cf6fd408191992b7f3b0394069c).
Existing public audience and runtime environment revision1 are preserved.
Final native Chrome inspection shows Gemini, the three tabs, model unavailable,
Google funding failure and disabled Run/Simulate. No form was submitted. The
existing key remains installed privately; no new transfer or inference occurred.

Prepared Store composition, original browser Start negotiation, native fixed
progress messages, atomic pending Stop and hash-checked physical recording/Range
routes now pass84 required offline cases. Twelve cases specifically use the real
Store/quiet serializer/controller with a mock station and synthetic real encoder.
Source-to-archive186-file hashes match. Package remains local: production worker
still e075e8d3 and is not physical-ready. See [evidence](../evidence/physical-store/)
and [lifecycle scope](PHYSICAL-LIFECYCLE.md). Offline footage is not robot proof.

| Requirement (ordered as above) | Current evidence and unmet acceptance |
| --- | --- |
| 1 Website/source | Passed: Site8 and public shared integration source; publication receipt |
| 2 All public demo materials | Site/source/evidence public; real method simulation and physical artifacts not produced |
| 3 Actual approach labels | Gemini Robotics source/run records; real selected-method execution still unverified |
| 4 Model choice/provenance | User selected Hydrogen; official pinned refs retained; prior402, no actually resolved successful model run |
| 5 Editable human identity | UI fields and offline fixture verified; current final page fields empty; real attributed queue path not exercised |
| 6 Run context | Private attribution and public method separated in tested serializer; actual physical run missing |
| 7 User/system attribution | Confirmed-human path retained; synthetic offline identities explicitly test-only; no new real queue admission |
| 8 Command contract |84 required cases pass through canonical validator/compiler/serializer; actual new worker deployment/qualification pending |
| 9 Representative task | No verified manipulation/object outcome; scene/contact reconstruction remains open |
| 10 Physical website execution | Public robot API503 before dispatch; YAM1 has no connected station |
| 11 Live arms during method | Final page shows camera gaps; no active method/physical run |
| 12 Immediate physical replay | Source/fixture playback tested; no matching real execution/footage |
| 13 Historical physical replay | History/fixture selection tested; no real physical history |
| 14 Corresponding simulation review | Retained bound attempts/UI implemented; no successful selected-model task simulation |
| 15 Run/Home-to-motion targets | Original Start retained; no actual Home/onset/correlated physical clocks; targets unverified |
| 16 Persistent real waits | Offline native boundaries, pending Stop and final status verified; actual deployed model/robot lifecycle missing |
| 17 Final normal-UI physical audit | Not run; external prerequisites unresolved |

Checklist remains **1/17**; no visibility or acceptance exceptions adopted.
At01:19UTC public health reports online/e075e8d3, google_prepay_depleted and both
readiness flags false; canonical YAM1 station list is empty. This is retained
provider failure state, not a fresh billing-balance query. Last SSH no-op timed
out on the existing front22 route. Automatic review denied the external public-IP
lookup/persistence for SSH repair as unapproved network-address disclosure; no
lookup or firewall change occurred. Google funding, station recovery and the
requested temporary SSH-repair authorization remain unanswered. These same
external blockers persisted across at least three consecutive goal turns.
No model substitution/retry, spending, identity/queue POST, motor command or email.
