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
- [x] Everything in the playground demo is public by default, including the
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
- [ ] Task acceptance matches the advertised capability and tested deployment.
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
- [ ] The person can browse/select previous runs on the website and replay their
  retained physical arm footage, associated with the executed method and run.
  Mock animations do not satisfy either replay requirement.
- [x] If the integrated method executes anything in simulation, those executions
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


## Kinex integration evidence — November 12, 2026

User invocation: “Acutally lets do this, lets just launch it and see what happens. Lets use the harness and make a new website”. This follows the discussed Astra/Codex + Kinex configuration. The user's confirmed runner identity was received privately in chat; no private email is stored in this repository.

Approach: **Kinex**, native core/MCP 1.0.0 from kinex-plugins revision `f68a8d7f1ddcae2b096f171b817c232d8730f3ec`; host Codex 0.162.1. Underlying planning/vision model `gpt-6-astra`, reasoning `low`, immutable resolved ID unavailable. Native tool catalog is device/devices/servo/device_stop. Python/shell, Cartesian motion, arbitrary onboarding and simultaneous/superseding buffers are excluded in this stationary joint/gripper adaptation.

Software evidence: thirteen command-contract and bridge regression tests cover both arms, exact gripper endpoints from fractional starts, pacing, preservation, stale/safety rejection and zero physical dispatch. The real canonical serializer/validator is used with a wire spy. Two website tests use real SQLite SQL and cover CSRF, private email redaction, one active run, claim-once semantics, owner Stop and non-revival of cancellation. An authentic Kinex MCP lifecycle test reads the local world clock and verifies unrestricted execution is absent. Required release gate is `preflight.py`, with source-hash-bound receipt checked by the outbound worker. These are offline software checks, not physical evidence or a dynamics simulation.

Model evidence: the non-actuating Astra/Codex check started actual Kinex, inspected schemas, read only world time, and shut down successfully. Parent-measured wall time was 71.20 s. An earlier attempt failed at MCP startup because required environment variables were not forwarded; that evidence is preserved privately and the corrected check passed. No robot connection or actuator command was involved.

Current hardware blocker: the supported Session API returned YAM1 hardware feedback with `safety.ok=false`, `reason=hardware_not_initialized`, `homed=false`, `settled=false` and a stale observation timestamp. Physical Run stays disabled while feedback is stale/unsafe. No physical Kinex run has occurred. Physical onset, Home/queue-adjusted timing, object outcome, live-arm verification and immediate/historical Kinex replay remain unverified. This integration is **not complete**.

Website: https://kinex-blupe.andlyu.chatgpt.site (public deployment v1 succeeded; reviewed v2 prepared). Public website source: https://github.com/andlyu/blupe-kinex (public main source verified). Shared runtime remains in codex-runner. Publication and scoped physical verification are authorized by the retained invocation and copied contract; no visibility exception was requested.

Review repairs: full canonical dispatch acknowledgement is checked before driver success; cancellation is rechecked after blocking reads and before model spawn, late acknowledgements cannot report success, gateway Stop failures remain visible, owned processes are reaped, and measured joint plus gripper agreement is checked before buffer completion. The explicit 0.02 normalized gripper target-agreement tolerance is additional validation, not the canonical sensor endpoint-drift rule or proof of object grasp. Upstream source/snapshot/installed runtime fingerprints are bound to preflight. Website repairs distinguish worker connectivity from robot readiness, hide broken-image chrome, retain action errors through polling and restrict Stop to the owner browser.

Public delivery evidence: Site project appgprj_6af56e0b68d081918ee61c1c8fc36d22, v1 commit b41e8c44fac0b33a75b53f9eec5e88e732cf404a, deployment appgdep_6af575b4c8f08191a7dff9081614ab38 succeeded. Public GitHub main has the same source. The public state endpoint confirms worker connected, ready=false, stale YAM1 feedback and zero runs. Current acceptance: public website/software preview and non-actuating model check verified; physical run/live motion/timing/replay/object outcome remain unchecked.

## Final handoff review — November 12, 2026

Website v2 deployed successfully from cd35227ae3b9bf95d74baeb92660f25f48a36686; final narrow UI recovery fixes were deployed as v3 from f8670751f35e0930cd1d28646de59a530f374edd. Public website source is https://github.com/andlyu/blupe-kinex . Native runtime source is https://github.com/andlyu/blupe-remote-bots/tree/codex/kinex-playground/codex-runner/integrations/kinex ; draft review https://github.com/andlyu/blupe-remote-bots/pull/311 . Clean source commit e1a3aa95aeb0aa7ae272333ce02a24b4ed57335d passed required CI: https://github.com/andlyu/blupe-remote-bots/actions/runs/43183812183 .

Seventeen acceptance items reviewed individually: website/source existence, public visibility for created materials, actual approach naming, adopted/configured underlying model, actual human identity in the non-actuating model check, and explicit no-simulation-rollout explanation are verified. Those six items are checked. Human join with editable defaults is implemented and the confirmed identity was prefilled privately in the delivered browser, but no queue join occurred, so that acceptance item remains unchecked. Physical run context, full advertised primitive coverage through native runtime/controller, representative physical task, real-arm live viewing, immediate replay, historical replay, every-run visual onset timing, complete live wait-stage behavior and final normal-UI physical run remain unchecked. Offline tests are scoped evidence, not a substitute for these requirements.

No visibility exception or timing exception is claimed. Model-clock test was non-actuating and is not a physical run. YAM1 currently reports hardware_not_initialized, not homed/settled and stale feedback. The public state endpoint shows worker online, ready=false and zero Kinex runs; Run remains disabled. No uncertain/timed-out motion has been retried. The integration is not complete.

UI evidence: published desktop/mobile layouts and disabled readiness state were visually inspected. A fresh finish reviewer assessed the inherited operational design; its owner-aware controls and readiness wording are resolved, and narrow camera/error-recovery fixes were resolved in the fresh reviewer's scoped verdict (ship). Running/replay/physical UI states remain unverified. Source screenshots contain no private email. The site and one outbound worker remain running; source/UI code, real Kinex/Astra connectivity and clean-source software checks are delivered.

Final website release: v3, source f8670751f35e0930cd1d28646de59a530f374edd, public GitHub main synchronized. Native deployment succeeded. Design documentation was independently rechecked after recovery-logic edits; no material mismatch was found. No physical acceptance claim was made.


## Verification continuation — November 12, 2026

Native command coverage was expanded through actual Kinex MCP/core and JSONL drivers, the production authenticated bridge, real RunnerController and canonical serializer/validator against a loopback-only synthetic station. The final isolated preflight passed 15 Python tests, including 124 native cases, 60 wire-spy packets and 50 rejection cases, plus the native MCP lifecycle. See [command coverage](COMMAND-COVERAGE.md) and [hash-bound receipt](evidence/preflight-native.json). Gripper reads now report their measured normalized fraction. The worker's preflight binds this exact source and pinned installed runtime.

The inherited visual/FK model has robot collision masks disabled. A failed contact-generation probe is retained, and the rejection branch is tested only with explicitly injected contact evidence. Local predictive collision protection is not established; no collision masks or remote safety limits were weakened. Full command-contract acceptance remains unchecked pending remaining safety/calibration coverage review.

Replay discovery is now implemented against the actual public recording index. It matches exact episode, YAM1 and Kinex attribution, validates playable URLs and labels accelerated previews. Atomic partial status updates and guarded recording writes preserve concurrent recovery. Seven real-SQLite Worker tests cover identity redaction/ownership, queue/claim/cancel behavior, attribution and URL rejection, unavailable lookup timestamps and both recovery races. A fresh scoped reviewer scored all three replay/data-recovery fixes resolved (ship); the design documenter found no new material drift. These tests use synthetic index entries and do not satisfy physical replay acceptance.

The latest supported YAM1 read still reports stale hardware feedback, hardware_not_initialized, homed=false and settled=false. No Kinex queue entry or physical command has occurred. All 17 checklist items were reviewed again: 6 verified, 11 unchecked. Identity/queue confirmation, actual run context, full command-contract gate, representative physical task, physical execution/live footage, immediate/historical replay, onset timing, live wait transitions and final normal-UI physical run remain unmet. No timing, visibility or physical-test exception is claimed.

Release safety state: the offline preflight is passed; `physical_command_contract` remains `pending_station_safety_calibration_review`. The outbound worker refuses hardware readiness until that required coverage is verified. A later station reconnection alone cannot enable Run. Runtime fingerprints include source/runtime files and exclude derived Python bytecode caches, which native tool imports may create.

Website v4 is deployed from source `95d67463c6d0cc3f4e34b039d28be2289a7eb02e` (deployment `appgdep_6af582afe064819195f25ab8ce19430d`, succeeded). Public GitHub main synchronized. The source-only replay fixes are verified; no external physical recording or playback was available. This continuation does not change the six checked / eleven unchecked acceptance count.


## Blocked audit — November 12, 2026

Previous goal turn was progress: native command-path coverage, replay recovery fixes, source publication and Site v5 deployment changed authoritative state. This third consecutive goal turn revalidated the same external hardware blocker rather than restarting a timed-out process. The owned outbound worker handle 17568 is confirmed live; zero Kinex runs exist. Supported YAM1 hardware feedback remains about 5,891 seconds old, with safety.ok=false, hardware_not_initialized, homed=false and settled=false. No queue entry, identity submission, physical command, movement or recording occurred during the audit.

All CI for runtime source `f90d9ff130f64f7f438d90553de63fe4af6116bb` is now terminal and passed: [Kinex command contract](https://github.com/andlyu/blupe-remote-bots/actions/runs/43189816912), [shared runner PR](https://github.com/andlyu/blupe-remote-bots/actions/runs/43189816576), [shared runner push](https://github.com/andlyu/blupe-remote-bots/actions/runs/43189806818), and [RoboHarness contract](https://github.com/andlyu/blupe-remote-bots/actions/runs/43189816573). No failed or pending CI is used as physical evidence.

The supported static calibration endpoint is available with the arms off. Its native joint calibration matches the pinned `6b24647ab8fe4b87dcee2cfb0100b1df8a7b8133ac8839bb37b0ba1cf37260df`, native_i2rt_updated convention and zero additional offsets. Its report-level camera calibration ID is a different, separate identity. The response includes retained nested safety provenance but does not establish the current active controller safety configuration; quality remains experimental_requires_fresh_validation. See [compact audit evidence](evidence/blocker-audit-calibration.json). A stale pose or static report cannot substitute for fresh station readiness or validate collision geometry. The existing pending physical-command gate remains in force.

Current public website is v5, source `441dbfd12d7bf9c107f97b18958787569e33a535`, deployment `appgdep_6af583f4d5108191951167141b2b8e18` succeeded; public GitHub main is synchronized. The software/UI runtime is delivered; the integration is not complete. Current acceptance remains six checked and eleven unchecked. Remaining items are human queue/join confirmation, actual run context, full command-contract safety/calibration acceptance, representative physical task, physical execution, live moving-arm footage, immediate replay, historical replay, per-run physical onset timing, live wait-stage transitions and final normal-UI physical run. No timing, visibility or physical-test exception is claimed.

External condition needed to resume: restore and initialize YAM1, obtain fresh safe hardware feedback and verify the active controller/safety/calibration binding. Then finish the existing mandatory command-contract review and perform the previously authorized bounded physical verification through the normal website. Do not enable Run by editing the pending marker alone, bypass readiness, fabricate footage, reset timing clocks, or replay an uncertain movement. Confirmed human identity and original user invocation remain valid; no duplicate permission request is needed for covered verification. The local worker stays live with Run disabled.


## Robo-house continuation — November 12, 2026

User resumed with “lets finnish” and selected Robo-house YAM (“why not run on robohouse YAM?”). The target is now robot-ba8413962083809c. The current live queue confirms it connected, parked and queue-ready with fresh hardware status. YAM1 is disconnected; its observation's old queue-ready flag was cached. Queue admission and controller-owned initialization/Home are distinct from actuator readiness; no motion is permitted before fresh, homed, settled safe feedback and a valid lease.

The Robo-house profile binds model calibration 93c4db966dca49dbb831a2215f4dfc5fb83bf82eabfe99b3035a027aa7fc9275, original_i2rt_model_corrected coordinates, 0.62 m base spacing, the exact offsets in the model's refs, model XML hash 22ed2648615c1e2fa8dfb0428e1b62d75a7a363374d6ce4b7bafe09ed5987edf and safety hash 172afc8a82d2b04fb03404e20ae5342a9272bdaae520b77e7caaa1e0c57bd965. Commands remain original encoder coordinates with no extra offsets. The live report must match before a write and again before buffer construction. The saved configuration is an additional local check; the gateway independently validates every leased command with its active configuration.

Robo-house adds the exact canonical HardwareSafetyConfig/BimanualHardwareGuard source snapshot, swept FK workspace/table clearance and an actual collision-enabled model. Collision masks are set before MuJoCo compilation, so cached body masks are also valid. Only the two assembled world/first-link base bearings are excluded because the meshes have a fixed 6.1 mm assembly overlap; all free inter-arm/link and floor contacts remain enabled. A fixed in-workspace joint fixture produces real model contacts and rejects before dispatch. No remote safety setting is changed.

The strict joint-endpoint regression exposed degree/radian round-trip rounding outside a legal bound. Only an already validated requested radian target's wire encoding is moved inward by at most four floating-point degree ULPs; all restored radians remain within the unchanged strict envelope. Invalid requested targets, including nextafter just outside a bound, still reject. Exact uninstructed measured joints are preserved. The failing preflight receipt and green regression are retained. Some legal joint endpoints are spatially inadmissible and correctly return workspace/collision rejection with zero outbound commands; tests do not disable those checks to force acceptance.

The isolated required gate passed 28 Python tests, including native MCP/core/JSONL-driver/bridge/controller/serializer runs for both stations: 124 native cases each, 60 YAM1 wire-spy packets and 56 Robo-house wire-spy packets. Source, mesh, controller snapshot and upstream/runtime fingerprints are retained in evidence/preflight-robohouse.json. Seven real-SQLite website tests pass with Robo-house camera/history attribution. The Robo-house command-contract item is verified in software; YAM1 remains physically ineligible. Physical run, outcome, live onset/timing and real playback are not established by these tests.


### First normal-UI attempt and compatibility repair

Site v6 (378e51b92c4078963a4e29d65857483a1d1fc13d) deployed successfully and its three Robo-house camera views were inspected live. andrew's confirmed name/private email were prefilled, editable and submitted through the normal Run control. Job 81581277-d1c5-4a34-a783-ed5b906a248a created backend session sess_d1eae5a0bd8e40b7. It stopped before any episode/model request/actuator packet because the worker referenced RunnerController.busy(), absent in the pinned controller. Public metrics show zero accepted/executed/confirmed waypoints; the normal queue was empty afterward and Robo-house remained parked/queue-ready. No timed-out or unknown movement was replayed. The public session overview is access-controlled (403); that restriction was respected.

The worker now derives active/terminal behavior from the controller's supported status snapshot and keeps readiness false through cleanup. A required whole-worker regression exercises real pinned RunnerController with a synthetic queued/Stop transport and no model or actuator dispatch; the previous code fails and the repair passes. See queued-worker-regression.json and preflight-robohouse-worker.json. The full gate now passes 29 Python tests plus both stations' native tool cases and the lifecycle gate. Automated verification has an explicit execution-mode CLI flag, separate from human identity. The first attempt's interactive metadata is retained as history; the next root-driven test is explicitly automated_verification.

Website request validation now matches the existing backend's minimum 60-second run and maximum 32-character runner name, with regression assertions. No source or public API response contains the confirmed private email. Human join/identity collection is verified even though execution failed before an episode; current software/join acceptance is eight of seventeen. The remaining nine items require actual method/run context, representative physical outcome, physical execution/live footage, immediate and historical replay, onset timing, live wait-stage verification and final normal-UI physical run. No physical or timing acceptance is inferred from this failed attempt.


### Second normal-UI attempt, status repair and recording recovery

Site v7 job `25fda63b-b886-4ed4-940d-a8f1d69a2537`, backend session `sess_78089e0503ef47a9`, episode `ep_9664b64abe26457c`, was admitted on Robo-house and completed controller-owned Home. Kinex/Astra performed real camera/state reads. A left-gripper 0.5 buffer (2 seconds, 20 waypoints) reached `packet_submit` for `traj_ep_9664b64abe26457c_0` at 1794494745.933030; Stop was requested at 1794494746.284991 and stopped at 1794494747.037345. No acceptance or measured-completion receipt was retained. Its execution outcome is uncertain, and this movement must not be automatically replayed. Zero last-published counters do not establish zero physical dispatch.

The worker status poll failed because `kinex_command`/`kinex_feedback` used integer metadata named `waypoints`, a reserved list field in the actual controller journal compactor. The metadata is now `waypoint_count`. The native command gate now wires the real controller journal and status compaction through actual native tools and dispatch. Restoring the old integer metadata in an isolated child reproduces the same TypeError; the fixed pinned release passes 29 Python tests and the native lifecycle/direct-schema/explicit-deny checks. See `evidence/status-compaction-red.json` and `evidence/preflight-direct-tools.json`. No hardware safety or packet bounds changed. The isolated source excludes unrelated shared-controller changes in the current working checkout.

The old MCP catalog required repeated discovery calls: the first packet was submitted about 74.7 seconds after model start, so no timing pass is claimed. The new facade directly exposes the four native Kinex schemas through the official RuntimeSession/core. The authorized host activates it; explicit Kinex denial, cancellation and Stop still use upstream handling. Fresh initial camera images/state are supplied to Astra. Actual latency remains to be measured.

Site v8 source `aec8287bba85cc9b14aad60263e1d10da47012db`, deployment `appgdep_6af5d83a7820819183663db1b1fa5d48`, succeeded. The recording index omitted its model; an exact independently matched public queue record confirms the same episode, Robo-house station, Kinex approach, andrew and task. Recovery retains `recording_index_model: null` and `attribution_source: matched_live_queue_context`; it rejects explicitly conflicting attribution. Eight real-SQLite tests pass. Its retained preview hash is `738fa8719964ba2bdf2f884099e0e654651c0b03b547a6f9549f38a36e70ef7c`, 32.533 seconds, marked 2x and EDITED REPLAY. The top-only edited footage does not clearly settle the uncertain gripper command or establish precise physical-onset timing. Ownerless session/trace access returned 403; reading the stopped trace through its original owned worker was prevented by macOS task-port entitlement restrictions. No access protection or OS privilege was changed and no credentials were copied. Future runs now retain private ownership, independent transport receipts and final backend traces.

The failed physical attempt, old timings and unknown command remain history. Physical task success, successful method-motion playback and final normal-UI acceptance remain unchecked. No timing exception is claimed.


### Verified physical wrist and gateway feedback repair

Normal UI job `dac55616-1277-4b79-8445-1987c7e4b924`, episode `ep_1dcfbe6dca464637`, session `sess_f594014f1e4c4d7e`, executed one right-wrist +0.08 rad buffer on real Robo-house through Kinex/Astra. All ten ordered waypoint receipts and a completed gateway result were retained privately; sanitized evidence is `evidence/robohouse-attempt-03.json`. Live cameras visibly showed the wrist move. The packet's measured final wrist was 3.3113 degrees and the existing target tolerance passed. No other task primitive completed. Normal Stop/parking released the lease. The previous uncertain left-gripper command was not replayed.

The adapter then stopped on the capability-scoped gateway observation's omitted source field, even though the shared controller had corroborated fresh hardware and settled completion. The repaired adapter independently reads fresh safe settled hardware under the same lease and validates both gateway and live measured targets; it does not merely trust a missing source. The gateway defines `homed` as currently being at Home, not initialization history. Startup Home is now independently verified once and bound to the session/episode/lease; following writes still require fresh safe settled hardware, unchanged lease, strict calibration and swept controller guards. A changed lease or absent initial Home still rejects. The episode binding is preserved when the public hardware snapshot omits it.

The old completion function reproduces the failure; see `evidence/hardware-feedback-red.json`. The exact isolated release passes 32 Python tests plus native direct-schema, explicit-deny and lifecycle tests; every native fixture now uses the real gateway's missing-source completion shape. See `evidence/preflight-hardware-feedback.json`. All public/private source distinctions and guards remain intact.

This physical run missed onset timing. No 15-second/30-second pass or timing exception is claimed. The attempted timed screenshot helper produced no frames; live screenshot observations and retained backend receipts establish a wrist motion, but do not constitute the required continuous UI timing record. That requirement remains unchecked. The new prompt supplies actual loaded device IDs, radians, profile bounds and exact native write syntax, reducing unnecessary discovery; its latency must still be measured.

The integration remains incomplete pending a full representative task, browser-playable method footage, timing/wait-stage verification and final normal-UI acceptance. Earlier source-only successes remain history rather than substitutes for these requirements.


### Strict freshness clock window

Site v9 source `c8fa16ac62366128c67b516fc5c7487168907b58`, deployment `appgdep_6af5dd13e0d08191ba7e694b01124f8e`, succeeded. Replay UI preserves its video/error/link across unrelated history refreshes by run ID and validated URL; a fresh reviewer marked the persistence fix resolved. The small-screen history gives each long task the full width. Public GitHub main is synchronized.

Normal UI job `c8a1639e-56ea-424b-b68b-10ba454be7c7`, episode `ep_3f2c1a734a6b4754`, stopped during independent startup feedback verification, before Kinex model startup or any actuator packet. The public timeline shows a hardware clock lead (one snapshot was timestamped about 12ms after local receipt); the old adapter rejected all negative ages. The exact rejected read did not retain its detailed age, so clock lead is a supported diagnosis rather than a claimed direct measurement of that read. Timed direct UI captures were successfully saved for this run (143 camera/actions frame pairs over 20 seconds), unlike the previous helper attempt. Home/parking is preparation, and no method-driven motion or timing pass is claimed.

The adapter now waits, cancellably, at most 0.5 seconds for a small remote timestamp lead to enter the unchanged strict local 0–2 second freshness window. It uses no future timestamp for actuation and still rejects larger future dates, stale data, changed lease, wrong station/source or unsafe feedback. Detailed rejection metadata now makes any recurrence diagnosable. The old read fails the new regression; the repaired isolated release passes 33 Python tests plus native/lifecycle/explicit-deny checks. See `evidence/clock-window-red.json` and `evidence/preflight-clock-window.json`. This is read-only clock handling, not permission to retry an unknown physical command.


### Representative run and publication timeout

Site v9 / runtime `c106ad820abd4379ccfee5a107addad66940d097` normal UI job `25f59a9c-488f-4a65-8989-69d700a190e7`, episode `ep_8d367811e49d4fee`, performed the empty right-gripper close/0.4/open cycle (measured approximately 0.004, 0.399, 0.999), left-wrist +0.06 rad and return. Five packets / 52 waypoints have independent settled hardware confirmation. A sixth right-wrist -0.06 rad packet has complete gateway acceptance/progress/completion for all ten waypoints, but independent final hardware confirmation was still waiting when the worker stopped. The final right-wrist return was never submitted. The full task did not complete; the sixth packet is not automatically replayed. See `evidence/robohouse-attempt-05.json`.

The private worker traceback identifies a website status-publication timeout at `/api/runner/update`, rather than a robot send timeout. The model/controller continued independently while that response was pending. The repaired worker shortens Site call timeout to3s and retries only the identical idempotent status/heartbeat once. Claims, queue admission and actuator requests are never retried. An actual queued/Stop worker regression injects a lost status response after processing; it verifies the identical repeated update, single queue join and zero model/actuator activity. If publication remains unavailable, the worker stops as before. Final source also explicitly sorts attached camera images to match their prompt labels. Required local release preflight passes 33 Python tests plus both native station contracts and lifecycle/denial checks in `evidence/preflight-release.json`.

Planning, validation and execution explanations were observed inline below Run in the real deployed UI. The old recording's error/link/player persisted through this new run's history transitions, verifying the fresh reviewer's persistence fix. Immediate and historical recording discovery work and retain exact approach/episode/station attribution. Browser media playback still reports Unable to play media; the fallback source link is visible. Playback acceptance is not inferred from a valid MP4 or available Replay button.

The timed UI camera/actions frames are saved with actual local capture bounds and Run click bounds under output/kinex-review/robohouse-run-05. First gateway observation at1794498216.4750092 was settled Home, corroborated by the live frames. First method command was submitted at1794498238.317852; first gateway progress at1794498238.7612574 is not substituted for visual onset. First motion is beyond15seconds from Home, so mandatory timing remains failed; no exception or clock reset is claimed. A detailed visual bound and queue calculation will accompany final evidence.

A required Linux CI preflight failed while the local pinned macOS gate passed. Earlier CI lacked failure output/artifacts; source now prints failed-command output and retains the complete receipt as an artifact. Required CI and any resulting repair remain pending; local success does not hide that failure.


### CI fixture diagnosis and final timing audit

The retained Linux failure is `evidence/preflight-linux-fixture-failed.json`. Its actual error was `_run_started_at` missing from the synthetic running controller fixture after merging current main into the PR check. Production joins initialize that state; the fixture manually entered running state without its timing fields. The fixture now sets a real start timestamp, the existing180s run duration and no end timestamp. No production controller or deadline safeguard changed. A duration-field red receipt is preserved as `evidence/preflight-fixture-duration-failed.json`. The exact local isolated gate passes again; a new Linux CI result is required before claiming the CI repair verified.

All five normal UI attempts now have timing records in `evidence/all-run-timing.json`, retaining original Run boundaries and marking missing visual/Home times explicitly rather than inventing them. The final attempt's conservative observed visual onset is1794498238.158–1794498239.907, using the beginning of last clearly unchanged frame00224 and end of first clearly changed frame00236. Home completion is1794498216.4750092, so the observed interval is21.683–23.432s after Home. Run click bounds are1794498206.577–1794498206.780; onset is31.378–33.330s after Run with0s queue exclusion. There was no separately established wait behind another runner; queued status overlapping controller initialization/Home is counted. Both mandatory limits fail. Small hardware clock lead and screenshot acquisition uncertainty do not change that result. See `evidence/robohouse-onset-timing.json`. A37.1s privacy-safe camera/actions verification film was generated locally from266 timed frame pairs; later windows have an explicit gap and are not presented as a continuous full-run recording.

Current acceptance remains11/17 verified. Unchecked: representative full task completion; immediate and historical in-browser physical playback; mandatory onset timing; full startup/wait/recovery-stage acceptance; final complete normal-UI end-to-end acceptance. No timing, visibility or physical exception is claimed. Simulation review is explicitly not applicable: MuJoCo is used for predictive validation, not a policy rollout. The integration is not complete.
