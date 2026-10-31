# Persistent goals for research integrations

This is the research-integration workflow used by the repository's `AGENTS.md`.
Its acceptance contract is the existing
[completion checklist](COMPLETION-CHECKLIST.md#completion-requirements), including
the detailed timing, evidence, exception and final deployed-site verification
sections. Do not substitute an implementation plan or a successful robot packet
for that contract.

## Intake and durable context

When a researcher asks to integrate, reproduce or finish a paper/method as a
BluPe integration, automatically activate a native persistent goal in the same
coding-agent chat. The repository owner explicitly requests goal creation for
these execution requests; the researcher need not say `/goal` or "keep going".
Questions about a paper, brainstorming, a requested plan, and ordinary runner
maintenance remain conversational unless execution is also requested. A question
during an active integration does not complete or replace its goal.

Before substantive integration work:

1. Read the completion checklist. Reuse the integration's existing copy, or copy
   the full template into its documentation with every box initially unchecked.
   Preserve the requirement text and detailed verification sections. Reconcile
   an older copy with the current template; retain evidence, but recheck claims
   affected by changes. Do not reset a partially completed integration.
2. In that copy's **Integration and evidence** section, record the method/source,
   requested outcome, site/source repository, authorized scope and constraints,
   amendments, native goal identifier if exposed, progress and next useful action.
   Record only known identity and permission information. A missing detail is an
   open task, not permission to invent it. Keep this record usable after context
   compaction or resuming the chat; do not create a second lifecycle database.
3. Inspect the chat's native goal using its available goal tools (for example,
   `get_goal`). Reuse an unfinished matching integration goal. If none exists,
   use the host's native goal-creation tool (for example, `create_goal`) with a
   concrete objective naming the method, the checklist copy and authorized scope.
   Carry user-specified budgets; do not invent or reset a budget. Do not overwrite
   an unrelated unfinished goal: resolve the scope conflict with the user while
   preserving both work records. If the copy records an unfinished goal in another
   chat, resume that chat or use an explicit handoff before starting a second
   autonomous loop for the same integration.

A suitable objective is:

> Finish the requested <method> integration with BluPe. Satisfy every Completion
> requirement and detailed verification rule in <checklist-copy path>, with
> current evidence for the deployed site/source revision, public demo materials,
> Model-as-approach labeling, actual method and
> runner attribution, physical execution, live views, replays, timing and wait
> status. Work within <the user's scope and constraints>. Unverified requirements
> remain open; blockers and limits are not success.

Use the host's actual native interface, not a fabricated tool or an extra model
loop. For native Codex tools, creation/read/update are exposed by the host; in
interactive Codex the user-facing interface is `/goal`. App-server clients expose
`thread/goal/set`, `thread/goal/get` and `thread/goal/clear`. This instruction-based
harness does not run an app-server or install hooks into the robot policy runner.
If the host has no native goal support, say automatic continuation is unavailable,
retain the checklist/progress and report the needed goal-capable host. Do not
pretend a Markdown record activates background execution.

## Follow-ups and continuation

Follow-up instructions amend the same integration and checklist. Preserve its
evidence, identity, scope, goal identifier and budget accounting. Read queued
user input before choosing the next action; newer instructions take precedence
where they conflict. For a narrower request such as "just explain this error",
answer it without interpreting it as cancellation. An explicit pause, cancel or
scope reduction takes effect immediately.

Native Codex keeps goals in thread state and dispatches continuation when the
thread is idle, no work is pending and no user input is queued. Let that dispatcher
own continuation; do not add a timer, repeatedly submit "continue", create another
goal, or start overlapping turns. Do not continue while a command, review,
approval, GPU startup or user response is pending. Observe its result once it
arrives and then select useful work. A plan-only request does not authorize
execution. Interruptions and lifecycle controls remain with the user/system.

Before ending **every integration work turn**, and after each verification result:

- Audit the actual outcome against every checklist requirement and the latest
  amendments. Open the relevant files, test receipts, deployed site and recordings
  as required. In the checklist copy, attach an indented evidence line under each
  checked requirement, for example:
  `Evidence: [timed visitor recording](evidence/visitor.mp4) — run ID, tested revision and measured entry-to-motion interval.`
  Use real links and the observations they support. Leave missing, stale, failed
  or unverified requirements unchecked; record the gap and next action.
- Run the read-only structural audit from the BluPe Remote Bots checkout:
  `python3 codex-runner/integration-harness/audit_completion.py <checklist-copy>`.
  It compares the copy with the canonical requirements and rejects checked boxes
  without linked evidence, including missing/empty local artifacts. It neither
  executes commands nor fetches links. `ready_for_review` means the records are
  structurally present; it is not proof of site behavior or permission to complete.
- If work remains and an authorized useful action is available, take it. If the
  turn must end, save the latest evidence, remaining requirements and next action,
  and keep the native goal active so the idle dispatcher can continue.
- If an automatic continuation makes no tool call or repeats an unchanged failure
  without new evidence, do not spin or replay the same action. Inspect the cause,
  choose a materially different supported action, or report the specific unblock.
  Honor the host's no-progress suppression and blocked-state transition rules
  (including repeated-blocker thresholds); do not mark success to stop a loop.

## Stops and completion

Only an explicit user pause may become a model-requested pause; system
interruptions may also pause according to the host lifecycle. Resume or cancel
only through supported user/system controls. A budget/time/usage limit preserves
progress and remaining checks and stops substantive work; it is never completion.
For a genuine blocker, record the evidence, attempted alternatives, blocked
requirement and exact input/permission needed. Complete independent authorized
work first. Use the host's blocked state when its transition rules permit it;
otherwise report the blocker without inventing a lifecycle state or busy retrying.

Do not mark the native goal complete based on an agent's summary, all checked
boxes alone, passing unit tests, a successful plan, motion submission, or an
intermediate harness result. Require the structural audit to pass **and** inspect
the linked evidence against the full existing contract. In particular, perform
the checklist's final normal-UI verification on the deployed site and tie the
physical run, live view, immediate and prior replay, identity, simulation review
if applicable, both timing measures and wait/recovery behavior to that revision.
Every Run click needs its own recorded outcome. Only exceptions expressly allowed
by the existing checklist may satisfy their applicable requirement; record them
honestly and never turn a timing exception into a claimed <=15-second pass.

Then use the native completion tool and give the researcher the checklist link,
site/source revision, verification evidence, checklist status and explicit
exceptions. A successful goal-tool response does not replace that final handoff.

Goal activation adds no hardware, deployment, spending or messaging permission.
For physical verification, use only the existing standing/task authorization and
its concrete test notice, confirmed attribution, normal queue/lease, readiness,
motion validation, limits and Stop. Respect task-specific exclusions and enforced
denials; never automatically retry a timed-out movement. An excluded physical test
remains unverified and prevents completion under the unchanged checklist.

Native lifecycle references: [Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)
and [Codex app-server goals](https://developers.openai.com/codex/app-server#manage-a-thread-goal).
