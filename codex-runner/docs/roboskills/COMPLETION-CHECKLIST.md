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

## Standing authorization for physical playground tests

### Authorization granted by using this harness

The owner defines use of this harness as a task-scoped authorization grant.
When the user requests a research integration, playground fix or verification
through this harness, that invocation authorizes the agent to carry out the
covered workflow below. A task requested under user-adopted instructions that
select this harness also counts: retain the task request and the selecting
instruction as the invocation evidence. Reading or discovering this file alone
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

These actions are part of the invoked workflow. Do not ask for separate
permission for each covered identity submission, run, movement or recording.
Reuse confirmed identity/defaults; ask only for missing or ambiguous identity
or scope outside this contract. Keep execution mode separate from human
identity. The grant covers the task's integration and existing queue/run
destinations, not unrelated recipients or publication of private email.
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

Harness invocation does not override enforced sandbox, managed-policy or tool
permissions. Use the normal permission mechanism when required. If automatic
approval review explicitly denies an action, do not retry it through another
route. Report the exact denied action and stated reason, acknowledge the
invocation and contract already present, and leave physical verification
unverified. Continue independent work or a materially safer alternative;
otherwise request only the specific unblock. A documentation update alone does
not authorize retrying an already-denied action. Keep sandbox and reviewer
policy intact.

References: [Codex instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md#how-codex-discovers-guidance)
and [Auto-review context and denials](https://learn.chatgpt.com/docs/sandboxing/auto-review).


Invocation evidence: user requested “please use the harness” and connection through BluPe remote arms, then “Then lets continue”. Confirmed runner/defaults remain the same as prior physical website runs; execution mode is automated verification, separate from human identity.

## Completion requirements

- [x] A usable website exists, with an associated repository containing the
  website's source code. Record both links and the deployed source revision.
- [ ] Everything in the playground demo is public by default, including the
  website, source repository, runs/results, live demos, recordings, replays/history,
  simulation outputs and supporting evidence. Any nonpublic exception reflects
  an explicit user instruction or visibility change, recorded below.
- [x] The website clearly names the actual approach/method being run. Use the
  executed method's name; Spotter is an example, not a shared hardcoded label.
  The **Model** field identifies the approach being tested, as specified below.
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
- [x] A person can use the website to run the integrated paper's method on
  physical YAM robots/arms. Record a verified physical execution of that method.
- [x] The actual physical arms are visible live on the website while the method
  runs, so a visitor can see that it is executing on real hardware.
- [x] Immediately after a run finishes, the person can replay that just-completed
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
- [ ] The website is intuitive: a new visitor, without coaching, can find how to
  run the method and have the physical YAM arms actually executing it within
  **15 seconds of entering the website**, verified as described below.
- [ ] **Mandatory for every run:** after the person clicks Run, the physical YAM
  arms start actual method-driven motion within **15 seconds**, unless that run
  requires launching a GPU as documented below. Verify and record every run;
  a sampled demonstration is insufficient.
- [x] Every meaningful wait after a website action is immediately explained in
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


## RoboSkills evidence — October30,2026

Status: INCOMPLETE / physical retest and recording-publication approval required.

- Website: https://blupe-bimanual-skills.andlyu.chatgpt.site/
- Website source: integrations/roboskills/site in this public repository; Sites production revision will be recorded in its VERIFICATION.md. Shared provider: src/remote_yam/roboskills_policy.py; launcher: roboskills_playground.py.
- Executed approach: RoboSkills; underlying inference model:gpt-6-astra. The provider uses pinned upstream core.agent.run with a BluPe-specific tool adapter, not the complete SAM/RoboKit tool surface.
- Human attribution: actual Andrew Lyubovsky from existing account context, editable name/email in the deployed UI. Public API omits email/capabilities. Physical test453a9a037e874840ad4382597c25e8c1 / ep_4518061f91c24d0d records Model=RoboSkills and the actual runner; automated verification is separate execution mode.
- First physical test:60-second maximum,20mm paired fingertip lift/return with grippers unchanged, normal queue/lease/readiness/Stop. Packet submission was followed by a status-lifecycle KeyError; it was not retried. Read-only native harness reconciliation confirmed parked=true and torque_off_verified=true. A complete method-driven lift/return is unverified.
- Corrected provider:17 tests and8 subtests pass. Pending-packet status is exercised. The corrected physical UI retest was explicitly rejected by automatic approval review (specific second motion test authorization missing). Public upload of the local real-camera recording was separately rejected (public disclosure authorization missing). Neither action was rerouted.
- Live physical camera evidence: deployed /#physical-yam loads actual top/left/right YAM-1 cameras through fixed public Session API paths; public camera request200. Queue and hardware_not_initialized/disabled state were shown honestly.
- Replay/history: physical history selector and receipt work; no physical recording upload was performed after the rejection. Existing footage stays in the user's local review output, not this repository. Immediate and prior physical replay requirements remain unchecked.
- Simulation review: /#native-verification, reference native-lift-20261030. Public native receipt/task/replay retained. MuJoCo demo solved8/8, overall build FAILED(robot_at_rest=false;scene_in_frame=false); fresh solver not run.
- Wait state: deployed Run immediately shows submission, then real BluPe preparation/running state; receipt and Stop remain inline. No GPU provisioning is used. Failed test is retained, not fabricated as success.
-15-second entry and per-run method-motion targets: UNVERIFIED / unmet. No paper/GPU exception is claimed. First run's method completion failed; the corrected test is approval-blocked.
- Public scope: site, source, live camera monitoring, public run metadata and native simulation evidence. Private email and capabilities are excluded. Anonymous shared compute was rejected earlier and remains disabled. Physical recording publication awaits explicit approval after tool denial.
- Standing physical-test authorization from this canonical checklist was retained. Enforced tool review remains controlling; no bypass was attempted.
- Remaining gaps: corrected physical method execution, timed entry/Run-to-motion evidence, immediate and historical physical replay, and successful native build/frozen-task solve.

Final code/evidence update: public source PR164; final Sites source d272543c470daaeed3c3f8b56f9ee77efd494116. All mirrored source bytes match. Corrected provider17tests+8subtests passed0.81s. Final TypeScript/build passed; SQLite migration equivalence and Drizzle no-change checks passed. New detailed model-wait wording is implemented but its corrected physical lifecycle remains unverified because the retest was denied; that checkbox stays unchecked.


## October 30 follow-up: standing authorization applied

The owner reaffirmed that physical tests are covered by the harness and asked
to resolve the approval mismatch. The same normal website Run action was
re-submitted with that clarification and concrete bounded scope. Review allowed
it; no robot command or safeguard was bypassed.

- Deployed source remains `d272543c470daaeed3c3f8b56f9ee77efd494116`.
- Website run `249450342a5e4286b9d406d3e8738d34`, episode
  `ep_a59c7a3174ef44c7`, was created by the actual website Run button at
  `2026-10-31T03:37:20.120Z` (October 30, 8:37:20 PM Pacific).
- The upstream RoboSkills Python agent generated one checked paired lift packet.
  Measured left/right fingertip rises were 14.04 / 14.38 mm against a 20 mm
  request. Its 3 mm tolerance check failed, so it ended without a hold/return
  attempt. This is verified method-driven physical motion, not a successful
  lift-hold-return task. Task success remains unscored. No uncertain motion was
  retried.
- The controller accepted the packet and matched measured completion. Normal
  `policy_complete` Stop was accepted. The documented YAM-control-harness
  read-only status subsequently returned `DISABLED`, `parked=true`,
  `torque_off_verified=true`, with auto queue still enabled.
- Live actual-arm footage remained visible beside the run controls. The new
  physical replay appeared immediately after this run and played in the browser.
  Clearing and reselecting this retained run in physical history reloaded its
  recording. Anonymous replay access returned HTTP 206 for bytes 0-1023 of the
  570,939-byte MP4, with no authentication supplied.
- Public replay: [actual YAM footage](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/249450342a5e4286b9d406d3e8738d34/assets/physical.mp4).
- Public receipt: [measured execution](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/249450342a5e4286b9d406d3e8738d34/assets/result.json).
- Name/email defaults remained editable. The website, retained run and local
  queue submission journal name Andrew Lyubovsky; Model is RoboSkills, with
  gpt-6-astra separate. The remote public station feed nevertheless showed
  `API caller`. Cross-surface attribution is not fully qualified. No email or
  visitor/lease capability is published in this documentation.
- The website visibly transitioned from submitting to readiness/queue, model
  wait, and finished/replay. Completed-stage retention and all failure/recovery
  paths are not fully qualified; the wait-stage requirement stays unchecked.
- The Run-to-motion target was missed: the checked packet was prepared at
  `03:38:01.716Z`, already 41.6 seconds after Run, before dispatch/physical motion.
  Planning took 27.28 s including 21.56 s model time; hardware execution was
  0.79 s. These are measured controller timings, not a claimed visual
  first-motion timestamp. There was no GPU startup and no timing exception.
  Site-entry timing remains unqualified.
- Automatic review still denied publishing the older failed-test recording,
  citing missing trusted authorization for that specific existing recording.
  It remains local; no alternate upload route was used. The pending specific
  authorization request covers that recording. Public-by-default qualification
  remains unchecked because this enforced denial is not a user visibility
  exception.

| Run reference | Run click | First observed method motion / evidence | Elapsed | Outcome |
| --- | --- | --- | --- | --- |
| 249450342a5e4286b9d406d3e8738d34 | 03:37:20.120Z | Real footage and measured packet completion; precise visual onset not separately measured | Packet not prepared until +41.6 s; actual onset later | Missed 15 s target; partial physical task |

Remaining qualification gaps: all-public older recording, full identity
consistency, site-entry and every-Run latency, completed-stage/failure UX, and
full final checklist qualification. The native simulation build remains rejected
with the frozen-task solver not run. This is not a complete research integration.


## Final lift/hold/return verification

- Tested website source `e983572f99c93cf41f4999f397bfb16e556548f2` (version9),
  deployed2026-10-31T04:17:24Z. User invocation and authorization-by-use contract
  were surfaced with exact Site/local runner/backend origins, YAM-1 both arms,
  confirmed Andrew Lyubovsky/name-email defaults,60s run limit,20mm task and
  new footage retained on the same Site. Execution mode: automated verification.
- Run `2ea288ea830e471a86eb6d1d98971c50` completed the lift, hold and return.
  The model generated the Python program in one upstream agent turn. Measured
  rises17.80/20.97mm satisfy the existing3mm target tolerance. Lift Cartesian
  errors2.21/0.98mm; return2.14/0.08mm. Grippers unchanged within0.0001.
  The measured interval from lift completion to return packet preparation was
  1.74s, including the program's1s hold and fresh feedback/preparation.
- Four packets matched measured completion. The first three formed the lift
  with bounded accumulated tracking correction; the fourth returned. No
  rejected/failed/timed-out/uncertain packet was retried. Model`RoboSkills`,
  underlying inference`gpt-6-sol`, actual human runner`Andrew Lyubovsky`.
  Native physical success score remains unset; this is a measured primitive
  verification, not the upstream paper's benchmark success score.
- [Real recording](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/2ea288ea830e471a86eb6d1d98971c50/assets/physical.mp4)
  appeared after completion, played and seeked through the website. Anonymous
  HTTP206/1024-byte range verified. Selecting previous retained physical runs
  was verified earlier; new and prior runs remain available in the same list.
- The website visibly retains completed queue/readiness, scene, model, motion
  and recording stages. The earlier accuracy-failed runs showed persistent
  exact measured failure reasons, retained footage and a new Run control. Stop
  was available during active execution. GPU startup not applicable: this
  subscription planner runs without provisioning a GPU.
- Native YAM-control-harness read-only status confirmed`parked=true`,
  `torque_off_verified=true`, mode`DISABLED`, automatic queue still enabled.
- Run click04:21:30.927Z; first packet prepared04:23:18.484Z (+107.56s).
  Queue/readiness consumed about97s; model6.31s, planning8.38s. This misses
  the15s requirement, with no GPU or paper-grounded exception. Exact visual
  first-motion time and new-visitor entry path remain unqualified.
- The earlier apparent handoff mismatch was not proven: the request later
  admitted normally. An unavailable station can reflect another active run.
  No other run was interrupted or readiness gate changed.
- Source-level tests: final focused22passed+8subtests/0.60s; broader shared
  suite1621passed,4skipped,254subtests/124.05s with CI-pinned ASPIRE+mink
  dependencies; Node358passed/0.695s. The additional accumulated-offset
  regression failed before its fix and passed after. Final CI records the
  complete current source. TypeScript and production build passed.
- The backend's legacy public conversation projection still labels the caller
  `API caller`; website, local submission journal and retained receipts use the
  actual confirmed runner. That cross-surface presentation issue is recorded,
  not hidden or claimed corrected.
- Automatic review still blocks uploading the original failed clip, citing
  missing trusted authorization for that specific existing recording. Its
  pending specific request is unchanged; no further upload attempt was made.
- An optional product question asks whether the owner explicitly waives the
  strict startup target for this version. Until answered, no waiver is assumed.
  Timing and full completion remain unchecked.


## Worker continuity recovery — October30,2026

- Interruption reconciliation found both task workers absent and both public readiness endpoints offline, with no active/queued Site runs. No interrupted run was replayed.
- Site version11/source `ca4ab9c843c49135e8845c87cbb00bf5cf6e42d8` deployed successfully at2026-10-31T04:41:14.680359Z, environment revision3. Separate `PHYSICAL_WORKER_TOKEN` and `SIMULATION_WORKER_TOKEN` isolate the two roles; existing operator-only control and public viewing remain. Secrets are not in source or output.
- `worker-agent/launch.py` starts a detached loopback provider plus configured workers, using stdin for secrets and persistent local logs/PID metadata. It refuses duplicate live services and occupied ports; it never kills, automatically restarts or replays a job. It requires this runner machine to remain awake; it is not an always-on hosting/reboot service.
- Provider/physical/simulation PIDs32026/32029/32030 remained alive after the launcher exited. Public Site `/api/config` returned online=true and `/api/physical/station` runnerOnline=true, queueCount0. This recovery verification initiates no Run/motion/recording.
- Two process regression tests pass (0.105s), including actual child survival after parent exit and duplicate rejection. TypeScript and production build pass. CI now also runs these launcher regressions.
- The final physical evidence remains run`2ea288ea830e471a86eb6d1d98971c50` against version9; version11's worker authentication/launch changes were verified without a duplicate motion test. Full checklist qualification remains incomplete: strict entry/per-Run15s timings, legacy backend caller-label consistency, original explicitly denied recording publication, and final all-requirements review. No startup waiver or visibility exception is inferred from “please proceed”.

Role authentication verified after deployment: each dedicated credential reaches its own worker handler (nonmutating unknown action404); cross-role requests reject401. No readiness heartbeat was fabricated and no run was claimed by these probes.
