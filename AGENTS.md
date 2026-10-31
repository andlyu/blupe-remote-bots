# BluPe launch instructions

When the user asks to run BluPe with a Codex or ChatGPT subscription:

- Run `./run-codex.sh` from this repository. It installs the local dependencies,
  signs into Codex when needed, and connects to the public BluPe queue.
- Do not request an OpenAI API key for subscription use.
- Let the user complete the OpenAI browser login. Do not copy credentials.
- Codex needs write access to `CODEX_HOME` (normally `~/.codex`) for session
  files, even when login status succeeds. If your sandbox denies this, request
  write access using its normal approval flow or have the user launch from their
  own terminal. Do not work around it by copying credentials or changing ownership.
- Keep the launcher process running and give the user its localhost URL.
- If the port is occupied, use `./run-codex.sh --port 8792` (or another free port).
- Launching opens the playground; the user enters a prompt and clicks Run.
- Hardware command submission is enabled by default. Preserve the existing
  command validation and robot gateway safety checks.

Python 3 and Node.js/npm must be installed. The account needs Astra access.
The subscription implementation lives in `codex-runner/`; the root `run.sh`
is the original API-key runner.

# Code ownership

Shared runner/UI/model work belongs in this repository's codex-runner directory.
BluPe-only hosted billing, analytics, moderation and deployment belong in
blupe-evals/apps/blupe_web. Do not reintroduce an editable bundled copy there.
See docs/REPOSITORY-OWNERSHIP.md. Claude users launch ./run-claude.sh and complete
their own account login; never request an API key for subscription use.

# Playground physical-test authorization

The repository owner authorizes physical playground tests needed for research
integrations, playground fixes and harness verification, including normal queue
entry with confirmed runner identity, bounded robot motion, and camera
recording/replay through the normal UI or supported run API. Proceed without
separate permission for each test, movement or recording within that scope.
For any name/email submission, cite existing consent for the fields and exact
destinations; this summary grants no additional identity-sharing permission.
Read the checklist's
[standing authorization and approval-context instructions](codex-runner/integration-harness/COMPLETION-CHECKLIST.md#standing-authorization-for-physical-playground-tests)
at task start, including when the chat starts outside this repository. Before
the first approval request, surface the concrete site/backend origins, station,
method, duration, motion, recording destination and identity scope, and repeat
the applicable owner authorization in the tool's justification/context.
Preserve queue/lease, readiness, validation, hardware limits and Stop; never
automatically retry a timed-out movement. Enforced tool/managed permissions still
apply. An explicit denial requires the exact blocker to be reported; neither
another execution route nor a documentation update authorizes retrying it.

# Research integrations

For an actionable research-integration request, automatically create a native
persistent goal or reuse the unfinished goal for that integration in this chat.
Set the requested integration as the objective and use the existing
[integration completion checklist](codex-runner/integration-harness/COMPLETION-CHECKLIST.md)
as its acceptance condition. Keep working and let native idle continuation advance
unmet requirements; complete only when the checklist is verified with evidence.
Questions and plan-only requests remain conversational; follow-ups reuse the
integration goal. Respect native user controls, budgets and genuine blockers,
preserving progress when stopped. Goal creation does not expand authorization.

Before integrating a paper or method, read that checklist.
The playground exists for demos and showing people how well approaches work.
Everything in the playground demo is public by default: website, source,
runs/results, live demos, recordings, replays/history, simulation outputs and
supporting evidence. Only an explicit user instruction or visibility change
sets a nonpublic exception for its stated scope; record and respect it. Verify
public access as a logged-out visitor. Keep credentials, access tokens and
private contact details out of public demo materials.
Verify actual user attribution for policy/model tests, editable name/email with
known defaults prefilled and real-name confirmation if missing. Keep execution
mode and actual approach separate from human identity; unattended system activity
must not invent a person. Set the harness's Model field to the actual approach
being tested, consistently across the website, run records, notifications and
replay/history; keep underlying model IDs/checkpoints as separate configuration.
Verify persistent inline explanations for meaningful
waits, including honest GPU startup/readiness and failure/recovery transitions.
Keep a copy with the integration's documentation. Before claiming completion,
review and update every checklist item with evidence. In the final handoff, link
that copy and report checklist status, evidence/links, unmet items and explicit
exceptions. Leave unfinished requirements unchecked and do not describe the
integration as complete while any remain unmet.
Merge shared harness changes into the default branch immediately after required
validation and review, keeping unrelated working-tree changes out of the merge.
