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
- [x] The person can browse/select previous runs on the website and replay their
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



## Historical initial UI review — November 4, 2026, 22:28 UTC

This section records the earlier pre-trial milestone. The current review below supersedes its then-current statuses and missing-identity statements.

User invocation: “Lets set up one experiment … add image noise to dream1 … make all the images 50% darker”; follow-up “launch a local ui with the ability to adjust the image brightness that gets sent in.” User subsequently selected “Fixed per run for a clean comparison” and said “performance compariosn can be relative.” The chat's adopted AGENTS.md selects this harness. No invocation is inferred from merely reading the checklist.

Requested local UI: http://127.0.0.1:8798. Backend: https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com. Spectator media: https://playground.blupe.io. Available stations: Robo-house YAM (`robot-ba8413962083809c`) and YAM1 (`yam-1`), both arms. This verification made no queue admission, model inference, identity submission or motion request. Actual task, duration and confirmed human attribution have not been supplied for an agent-run comparison. The UI collects editable real name/email before a launch; no name/email was invented or posted.

Implementation/source: local extension in `codex-runner/integrations/dream-brightness`, using the existing clean shared runner revision `77cee11e0916e084e83d3b96eaadecae8eb24bd6` from worktree 0227. Current task checkout starts at `bd4c7dce6fe52d25ab284d1422cc0817e52f7a83`; unrelated changes were preserved. No source push or hosted deployment occurred. The request specified a local UI; there is no claimed explicit user revocation of public defaults and no publication verification.

Model configuration: requested approach Dream1; UI defaults to existing `dreamlabs/dream-1-beta`, with the existing `dreamlabs/dream-1-beta-flash` option. Dream SDK/client 1.0.0 installed in an isolated Python 3.12 environment. No substitute model or random noise added. Provider availability and immutable checkpoint revision remain unverified because no inference was made. Brightness is configurable 0–200%, default 50%, snapshotted per run. Separate `image_experiment` configuration retains the factor, percentage, variant, all three camera roles and preprocessing; every run also writes `image-experiment.json` in retained local run data. Private email is absent from that experiment metadata.

Evidence directory (repository root): `outputs/dream-brightness-01a1a8a1/`. UI screenshots: `desktop.jpg`, `mobile.jpg`. Offline tests exercise actual DreamAdapter `_capture_tick` and its final JPEG/base64 observations: 50% channel means within JPEG tolerance, exact preview/policy byte equality for 0/50/100/200%, all three views, 320x176 JPEG, unchanged state/timestamps, invalid factors, preview regression and missing identity. No model/actuator call is used by these tests. Native Dream and trajectory suites are also run; final receipt `preflight-final.xml`. First broader run was 91 passed and 2 failures caused by test database writes to the read-only source checkout; test database destinations were then explicitly set to writable experiment outputs, without editing upstream source or changing control checks. Initial port-bind denial was resolved through the normal approved launch; no automatic review rejection occurred.

| Completion item | Current review and evidence |
| --- | --- |
| 1. Website and repository/deployed revision | Local website running and source present; public deployed revision not verified. Unchecked. |
| 2. Public demo/source/results | No publication performed for this local setup; no comparison artifacts produced. Unchecked. |
| 3. Actual approach label | Verified browser title “Dream1 brightness · Local experiment”, selected “Dream-1 beta”, actual adapter model identifier and brightness setting. Checked. |
| 4. Underlying model choice/provenance | Dream1 request retained; existing beta/Flash model IDs configurable. SDK installed. Provider availability/immutable alias and model execution unverified. Unchecked. |
| 5. Editable/confirmed identity | Existing editable name/email fields retained, missing/default placeholder names and missing email rejected before queue. No human join performed. Unchecked. |
| 6. Actual approach/identity in run context | Config adds `image_experiment`; no actual run/context retained yet. Unchecked. |
| 7. Actual human attribution in model tests | Offline tests use synthetic frames and mocked transport, no inference. Actual identity pending before model/physical tests. Unchecked. |
| 8. Full command-contract release gate | Existing Dream/trajectory regression suites run; actual deployed validator matrix not re-certified. No control code changed. Unchecked. |
| 9. Representative task acceptance | No actual task outcome measured. Comparison can be relative to the 100% baseline. Unchecked. |
| 10. Physical execution | Not run. Unchecked. |
| 11. Live physical method footage | Real spectator footage visible, but no experiment run occurred. Unchecked. |
| 12. Immediate replay | No experiment run/replay. Unchecked. |
| 13. Previous run replay | Existing service-backed run list visible; experiment replay selection/playback not verified. Unchecked. |
| 14. Simulation review | Not applicable: no simulation executed. Synthetic offline unit images are test fixtures, not a simulated robot run. Checked with explicit N/A. |
| 15. Every-run startup timing | No Run click, Home or method motion for this experiment. Unverified, no pass claimed. Unchecked. |
| 16. Wait/failure/recovery UI | Preview capture reason, actual completion, failure text and Refresh recovery observed. Native queue/model/GPU launch stages not verified for an experiment run. Unchecked. |
| 17. Final deployed normal-UI physical run | Local UI and previews verified; final deployed physical run not performed. Unchecked. |

Status: 2/17 checklist items checked, including one explicit simulation N/A. The local brightness controls and encoded image path are verified; the overall research experiment is not complete. Required remaining work: confirmed actual task/station/identity, paired baseline/treatment runs with scene/prompt/checkpoint/duration controlled, relative outcome review, timing/live/replay evidence and any required public delivery. Preserve normal queue, lease, readiness, hardware limits, Stop and parking/release. Never replay a timed-out movement automatically.

Browser verification: 50% default, 100% baseline, 50% preset and keyboard change to 51% observed; three real darkened camera previews loaded. Mobile at 390x844 had no horizontal overflow. Controls were restored to 50%; temporary viewport override reset. Fresh preview is explicitly labelled as a new camera capture, not the exact frame from an inference. No inference timing or performance improvement/degradation is claimed.

Final offline preflight: **93 passed + 6 subtests, 10.05 s**, `preflight-final.xml`. Actual JavaScript request-body test: **1 passed, 56.693375 ms reported test-run duration**. Launcher `--help`, shell syntax, JS syntax and diff whitespace checks passed. Reused runner tracked working tree stayed clean. Reproducible source hashes and verification summary: `outputs/dream-brightness-01a1a8a1/verification.json`.


## Historical review — November 4, 2026, physical pilot and retained local UI

**11/17 requirements verified (including explicit simulation N/A); integration unfinished.** Full actual scope, user invocation, model configuration, identity handling, physical outcomes, artifacts, timing boundaries and exceptions: [TRIAL-RESULTS.md](TRIAL-RESULTS.md). Private contact fields are retained only in operational/private storage, not this public-intended evidence.

The user's confirmed Andrew identity was supplied before model/physical tests. Both editable fields are prefilled through an owner-only private defaults file on this machine. Agent operation/review is separate from Andrew's human attribution. Requested Dream1 resolved to existing Dream-1 beta alias; actual SDK availability and physical execution were verified with no substitute. Immutable provider checkpoint is unavailable/unverified and explicitly recorded as such.

| Item | Current evidence and decision |
| --- | --- |
| 1. Website/repository/deployed revision | Local loopback UI and source exist; public hosted deployment and deployed revision not verified. Unchecked. |
| 2. Public demo/source/results | Native backend episodes exist; local source/evidence not yet published as an integration. No explicit visibility exception claimed. Unchecked. |
| 3. Actual method label | Dream1 brightness title, actual Dream-1 beta model, fixed brightness displayed. Checked. |
| 4. Underlying models/provenance | Explicit Dream1 request retained; actual dreamlabs/dream-1-beta and SDK/client1.0.0 used; configurable beta/Flash choices; provider alias lacks immutable revision and this is disclosed. No substitution. Checked. |
| 5. Confirmed editable identity | Andrew and user-confirmed private email supplied before tests; current editable fields prefilled from0600 defaults; missing identity validation verified. Checked. |
| 6. Run method/identity context | Both episode records, normal UI history and retained experiment ledger identify Andrew, Dream model and actual conditions. Terminal projection regression fixed/tested. Checked. |
| 7. Real user attribution | Both actual runs attributed to confirmed Andrew; execution mode is agent-operated UI/replay review, recorded separately. Checked. |
| 8. Command-contract preflight | Required verify.sh passes45 Python tests plus JS test. Actual Dream conversion/HTTP serializer -> exact deployed canonical parser SHA1c640b6d…; fractional starts, endpoints, invalid/zero-dispatch and lease/freshness checks. No motion-code changes. Checked. |
| 9. Representative task acceptance | Both complete task outcomes failed, initial scenes unmatched. No pick-and-place success or controlled brightness result claimed. Unchecked. |
| 10. Physical method execution | ep_17a7cf3b22d34fbf at100% and ep_9a2ff3550b444f7f at50%, normal UI60s Robo-house both arms. Checked. |
| 11. Live physical arms | Timed live UI images show real camera views during both trials; lag/stalls labelled. Checked. |
| 12. Immediate physical replay | Each native replay opened after its run; retained accelerated physical footage reviewed/seeking verified. Some camera segments missing; no continuous four-camera coverage claim. Checked. |
| 13. Previous physical replay | Both episodes selected through history; after reload still listed with Andrew, Dream model and Failure labels. Local retained MP4s linked in trial evidence. Checked. |
| 14. Simulation | N/A: no simulated robot execution; synthetic test fixtures and IK calculation do not constitute a simulation run. Checked. |
| 15. Every-run visual startup timing | Click/queue/Home/backend-progress timestamps retained for both; exact visually observed first motion and complete timed screen recording not established. Backend proxies alone do not certify this. Unchecked. |
| 16. Meaningful wait/failure/recovery UI | Queued/preparing/running/stopped/preview stages observed; camera catch-up honest. Full required failure/stall/recovery matrix not verified. Unchecked. |
| 17. Final deployed normal-UI physical run | Two local physical pilot trials verified. Final publicly deployed version/run absent. Unchecked. |

Normal native controller parked each trial at joint zero and disabled torque at the60s cap. Auto-queue remains normally enabled and other users' sessions were respected. No timed-out movement was retried. Harness helper's HTTPS-only scope renderer could not render loopback HTTP; exact actual scope and contract were surfaced manually before covered actions. The newer harness Launch endpoint404ed with write_started=false, followed by use of normal native operator controls, not a validator bypass. No automatic approval review rejected the physical actions.

Current live server http://127.0.0.1:8798, PID90655, exec session75260. Requested local controls/default50%, saved comparison, actual camera previews and editable identity defaults verified after metadata reload; temporary viewport reset. Source/receipt hashes are in verification-final.json. No further physical test occurred after the metadata-only reload. Keep the integration goal active until remaining checklist items are satisfied or genuinely blocked.


## Current review — November 5, 2026 UTC: selected calibration binding

**8/17 requirements verified; integration unfinished.** The physical pilot above remains history. Changed Dream FK/IK geometry reopens items10–12 for this revision; it does not establish physical accuracy or repair the independent inference-service disconnect. Items1,2,9,10,11,12,15,16,17 remain unchecked. Items3–8,13,14 retain their earlier evidence; the required command-contract gate now passes48 focused Python tests plus the actual UI JavaScript test, and202 core tests plus6 subtests pass.

[CALIBRATION-BINDING.md](CALIBRATION-BINDING.md) records implementation, dynamic operator-profile binding, original encoder preservation and the actual SDK synthetic solver check. Evidence in `../evidence/calibration/` includes numerical receipts and test reports. No model request, queue admission or physical command was issued for these calibration checks. Earlier unmatched0/1 baseline and0/1 darker trials cannot establish a brightness effect and must not be pooled with a new calibration fingerprint.

Loaded runtime commit487dd92f638d90e52e5769a3aac12b9af09ad125 was verified on localhost8798: the read-only inspection followed the temporary zero-trial profile and restored camera fit93c4db…9275; UI showed50% and the restored model/camera IDs. Receipts are in `../evidence/calibration/`. No model or physical run occurred. The expanded required preflight now passes70 Python tests plus the actual UI JavaScript check, including the22 calibration regressions. Public source delivery and hosted deployment remain unfinished. There is no explicit user visibility exception.
