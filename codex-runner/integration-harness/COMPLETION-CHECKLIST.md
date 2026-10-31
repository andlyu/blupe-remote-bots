# Research integration completion checklist

Agents and humans: read this before integrating a paper or method. Copy this
template into the integration's documentation, fill in the evidence, and check
each box only after verification. All boxes must be checked before declaring the
integration complete. Before the final handoff, review and update every item with
evidence. Report checklist status, evidence links, unmet items and explicit
exceptions; leave unfinished requirements unchecked and do not describe the
integration as complete.

For execution requests, first follow the [persistent integration goal workflow](GOALS.md).
This checklist is the goal's acceptance contract. Keep its requirement text and
verification rules in the integration's copy; add an indented
`Evidence: [description](artifact-or-URL) — observed result` line beneath each
checked item. Audit that copy with
`python3 codex-runner/integration-harness/audit_completion.py <checklist-copy>`
from the BluPe Remote Bots checkout, then inspect the actual evidence. Passing
this structural audit is necessary but does not establish site or physical
success. Keep the native goal active while authorized useful work remains.

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

## Standing authorization for physical playground tests

The repository owner authorizes agents working on BluPe research integrations,
playground fixes or harness verification to perform the physical playground tests
needed to finish that work. This includes joining the normal robot queue with the
confirmed runner identity, starting the selected method on the task's physical
robots/arms, actual arm movement for a bounded run, capturing and retaining camera
recordings, checking live footage and replay/history, and using Stop and normal
parking/lease release. These tests are part of the requested work; do not ask for
separate permission for each run, physical movement or recording. Reuse this
standing authorization in the integration's copy of this checklist.

Before a physical test, state the website, robot/station, method/task, run duration
and expected motion/recording side effects in a brief progress update. Include
that concrete scope and this standing owner authorization in any tool escalation
justification so approval review can see why the action is authorized. This is a
notice, not a new confirmation step; proceed without waiting for a reply.

Use the normal playground UI or its supported run API with existing queue/lease,
readiness, command validation, hardware limits and Stop behavior intact. Keep
tests within the task's robots, method and existing run limits, respect other
users' active runs, and never automatically retry a timed-out movement. This
authorization does not extend to unrelated robots or disabling safeguards.

Standing task authorization does not override enforced sandbox, managed-policy or
tool permissions. Use the normal permission mechanism when required. If automatic
approval review explicitly denies an action, do not retry it through another
route: report the exact action and stated reason, leave physical verification
unverified, and request only the specific permission needed to unblock it.

## Completion requirements

- [ ] A usable website exists, with an associated repository containing the
  website's source code. Record both links and the deployed source revision.
- [ ] Everything in the playground demo is public by default, including the
  website, source repository, runs/results, live demos, recordings, replays/history,
  simulation outputs and supporting evidence. Any nonpublic exception reflects
  an explicit user instruction or visibility change, recorded below.
- [ ] The website clearly names the actual approach/method being run. Use the
  executed method's name; Spotter is an example, not a shared hardcoded label.
  The **Model** field identifies the approach being tested, as specified below.
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
- [ ] The website is intuitive: a new visitor, without coaching, can find how to
  run the method and have the physical YAM arms actually executing it within
  **15 seconds of entering the website**, verified as described below.
- [ ] **Mandatory for every run:** after the person clicks Run, the physical YAM
  arms start actual method-driven motion within **15 seconds**, unless that run
  requires launching a GPU as documented below. Verify and record every run;
  a sampled demonstration is insufficient.
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

## Verify the 15-second path

Time a visitor's full path. Start at initial navigation to the website (`t0`);
stop at the first observed physical arm motion executing the integrated method
(`t1`). Require `t1 - t0 <= 15 seconds`. Include page loading, finding the controls,
login/setup, queue/readiness waits and inference in the elapsed time; do not
restart the clock at Run. Queued, submitted, accepted or a UI "running" status
alone does not pass, nor does backend latency alone.

Include join-time name/email entry or confirmation in this same measurement.

Record the visitor's starting state and test conditions. Keep a timed screen
recording showing site entry, the visitor's actions and the live arms beginning
the method, linked to the matching physical run. If the elapsed time exceeds
15 seconds or physical motion is unverified, leave the box unchecked.

## Verify every Run click

This is an additional per-run measure; keep the site-entry test above. For every
run, start at the Run click (`t_run`) and stop at the first observed actual
method-driven physical arm motion (`t_motion`). Require
`t_motion - t_run <= 15 seconds`, subject to the GPU-launch exception below.
An acknowledgement, accepted request, queued status, submitted action or inference
starting is insufficient.

Record every run below (add rows), including visual evidence of the click and
motion. Mark the outcome as pass, missed target, unverified or exception.
Exceptions are not fulfilled <=15-second runs.

**GPU-launch exception:** a run that requires launching/provisioning a GPU (for
example on RunPod) may exceed this Run-click target. Record why the GPU had to be
launched and its startup evidence for that run. Keep the full elapsed time from
Run click to observed physical motion; do not reset the clock when the GPU becomes
ready. If GPU startup causes the target to be missed, label the outcome as an
exception. If the GPU is already available, the normal 15-second requirement
applies. This exception does not change the site-entry measure above.

Other exceptions require a specific justification grounded in the integrated
paper/research, explaining why it applies to that run, plus a supporting source
citation/link and relevant section/page. Outside the explicit GPU-launch case,
slow loading, queueing, setup or infrastructure delay is a missed target, not in
itself a paper/research-grounded exemption.

| Run reference | Run click (`t_run`) | First observed method-driven arm motion (`t_motion`) / visual evidence | Elapsed seconds | Outcome |
| --- | --- | --- | --- | --- |
| | | | | |

- Exception record (repeat for each affected run):
- Exception category (GPU launch or paper/research-grounded):
- Affected run reference:
- Specific reason and why it applies to this run:
- GPU-launch evidence (if applicable: provider, instance/job reference,
  launch/ready timestamps and startup log/link):
- Supporting paper/research source (for other exceptions: citation/link and
  relevant section/page):

## Visible progress while waiting

Use a compact persistent inline status area directly below Run in the existing
run panel; keep other meaningful waits beside their initiating control. Show the
current stage and why it is taking time immediately, keep it readable throughout
the wait, and visibly mark completed stages as actual lifecycle state advances.
A transient toast alone or a generic spinner is insufficient.

When a model requires a new GPU, show only the stages that actually exist:
`Starting GPU` / "We're launching a GPU on RunPod for this model" -> `GPU ready`
-> `Loading model` -> `Running`. GPU startup must be explicit immediately after
Run; visibly confirm actual GPU readiness before subsequent loading/running and
retain completed-stage confirmation. Use the applicable provider/model wording.
On failure or a stalled stage, state the known condition honestly and show an
available recovery action, such as retry or cancel where supported. Do not invent
percentages, ETA or completion, or expose irrelevant infrastructure internals.
This transparency requirement adds no timing exemption or clock reset.

## Final verification before completion

Open the deployed website and its associated source repository. Use the normal
visitor flow to join, run the integrated method on physical YAMs and watch the
actual arms live. Check both 15-second measures, approach/runner identities,
replay of the just-completed run and selection/replay of previous runs. Review
every checklist item against current evidence, including public visibility and
actual user attribution in policy/model tests, with execution mode separate.
Check the website, repository and each demo artifact type as a logged-out visitor;
record working public links or the explicit user-directed visibility exception.
Verify that Model identifies the executed approach consistently in the website,
run records, notifications and replay/history, with underlying model/checkpoint
configuration recorded separately.
Verify wait status appears immediately, keeps a readable reason, and visibly
confirms real stage completion (GPU ready before subsequent loading/running).
Check failure/stall status and available recovery evidence too. Record the
tested deployment, run and evidence below.
Leave unmet or unverified items unchecked and report gaps and explicit exceptions
before any completion claim.

## Integration and evidence

- Native integration goal (identifier if exposed, objective, checklist-copy path,
  authorized scope/constraints and user-specified budget):
- Follow-up amendments (latest requested outcome/scope; retain earlier evidence):
- Latest goal audit (date, verified/open requirements, evidence, next useful
  action; pending work or blocker and exact unblock if applicable):
- Paper / method (link and version):
- Final verification (reviewer/date, tested website URL and deployed revision,
  physical run reference):
- Final checklist review (evidence for every item, replay links/timings, unmet
  items and explicit exceptions):
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
- Physical-test authorization/scope (standing owner authorization or task
  reference, website, station/arms, confirmed runner, method/task, duration,
  expected motion and recording; permission-review result if applicable):
- Physical execution (date, method/configuration, YAM station/arm IDs, run ID):
- Live physical arm footage (website location and evidence link):
- Just-completed replay URL / immediate availability evidence (same physical run):
- Previous-run browser URL / selected prior run and replay evidence:
- Simulation review (corresponding run reference, website review link, what ran
  and its results, suitable replay/visualization/outputs, clear simulation label;
  or explicit not-applicable explanation if nothing executes in simulation):
- 15-second test (tester/date, browser/session/network and robot readiness):
- Visitor's starting state and entry-to-motion steps:
- `t0` / `t1` / total elapsed seconds:
- Timed screen recording / matching physical run evidence:
- Remaining gaps:
