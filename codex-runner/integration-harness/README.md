# Adopt the research integration harness

The harness includes repo-local startup instructions and a scope renderer. Install
it into each integration before beginning implementation or physical verification:

```sh
python /path/to/blupe-remote-bots/codex-runner/integration-harness/adopt.py install \
  --target /path/to/integration
```

The installer puts the harness block first in the integration's `AGENTS.md`, copies
the checklist when it is missing, installs `tools/blupe_harness.py`, and records
content hashes in `.blupe-harness.json`. It also copies the exact authorization-by-use
contract into `docs/BLUPE-HARNESS-CONTRACT.md` and the required engineering gates
into `docs/CONTROL-CONTRACT.md`. Startup instructions load both. Existing instructions and completed
checklist evidence stay intact. Repeating installation is idempotent; edited
helpers and malformed markers are preserved with an actionable failure. Use
`--dry-run` to inspect changes or `--check` to return a nonzero status when setup
is missing or outdated. Start the coding agent in that integration so it loads
the repository instructions. A chat outside the repository must explicitly load
its `AGENTS.md` and checklist, as directed by its owner.

## Proceed within existing authorization

The contract records the permissions granted by the user's request to perform
the task through this harness. Retain that invocation and the adopted selecting
instruction. Reading or copying the harness alone is not an invocation. Covered
confirmed identity submission, queue entry, bounded movement, recording/replay,
Stop and normal release have standing owner authorization and require no
separate run confirmation. The integration request also authorizes publishing
its source repository and deploying its publicly hosted website, including
source pushes and normal visibility changes. Both must be public by default;
do not ask for another publication confirmation. Keep credentials, access tokens
and private contact details out of public materials.
The pre-test notice is progress, not a new permission question. Keep all normal
queue/lease, readiness, command validation, hardware limits and Stop checks.
Never automatically retry a timed-out movement.

For a boundary-crossing tool call, supply the existing owner authorization and
the exact operation in its approval justification/context. That evidence must
be visible in the surfaced request. A link or the agent's hidden reasoning is
insufficient. Prepare it with the installed, standard-library-only helper:

```sh
python tools/blupe_harness.py scope --target . --spec /path/to/private-scope.json
```

Start with `scope.example.json`; fill its placeholders using the actual task and
prior user instructions. Keep identity details and private task records outside
public source. The renderer requires exact HTTPS site/backend origins, station,
arms, exact action, approach, execution mode, task, duration, movement, recording destination, and the actual
user invocation reference. Name/email submission requires already-confirmed
runner fields, their confirmation reference and the task's exact operational destinations.
It refuses unfilled placeholders, credential-bearing URLs and unrelated identity
destinations. Put the resulting notice directly in commentary and the tool's
approval context before the authorized test.

Rendering a notice submits nothing and grants no consent. Cite real existing
consent; ask only for missing required scope. Preserve actual human attribution.
For publication, cite the contract and exact public website/repository in the
tool context; the physical-test scope renderer is unnecessary for a
publication-only action. Enforced sandbox, managed-policy and tool permissions
still apply through their normal mechanisms. The harness adds no authorization
gate for covered runs or public delivery. Report a platform restriction with its
exact action/reason and continue unaffected work; do not ask for the same covered
permission again.

No global Codex configuration, reviewer policy, robot service, or credentials are
changed by installation or rendering. Automatic review acceptance cannot be
guaranteed by repository text. Complete the physical/replay/timing checklist with
deployed evidence before declaring the integration finished.

## Timing contract and existing integrations

For every ordinary run, verify first observed method-driven physical motion
within **15 seconds after matched settled startup Home completion** and
**30 seconds after Run/Start excluding evidenced queue-admission waiting**.
Record the original Start, actual queue entry and matched first session/lease
grant, full wall time, excluded queue seconds and queue-adjusted time. Start-to-
queue-entry delay and post-admission preparation/Home/coding/loading still count.
Already-admitted/no-wait runs exclude zero with evidence; missing queue/admission
evidence leaves the Run measure unverified. This is normal 30-second budget
accounting and does not change the 15-second post-Home measure. Show actual queue
waiting, admission completion and subsequent preparation as distinct inline stages.
If Home is unnecessary, document the earliest per-run robot-ready boundary as
specified in the checklist; do not wait for model/code readiness to start that
clock. Home/preparation motion does not count. Site-entry
timing is contextual evidence. Keep both full elapsed times and timed visual
proof, with matched Home/readiness lifecycle evidence.

A genuinely new GPU launch must be visible inline for its entire real
start-to-ready interval. Keep full elapsed times and label a target miss caused
by evidenced GPU-launch blocking time as an exception. Only that blocking
overlap may be excused from each clock under the checklist's limits. Subtract
the union of queue wait and GPU blocking from Run: shared seconds count once,
not twice. Queue exclusion alone is normal accounting, not a GPU exception.
Warm GPUs, coding, model loading and post-admission delays receive no automatic
exception. GPU ready before Home leaves the full 15-second post-Home limit intact.

These illustrative timelines use seconds after Run and assume complete visual,
Home/readiness and (where applicable) persistent UI/lifecycle evidence. They are
worked examples, not physical verification:

| Scenario | Queue entry–admission | Home / motion | GPU launch and actual blocking | Full Run / post-Home seconds | Queue-adjusted Run seconds | Outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Ordinary run | No wait (evidenced) | 12 / 26 | None | 26 / 14 | 26 | Both pass |
| Queue-admission wait | 0–40 | 42 / 50 | None | 50 / 8 | 10 | Both pass normally; exclude 40 queue seconds |
| Post-admission preparation delay | 0–40 | 65 / 78 | None | 78 / 13 | 38 | Run misses; post-Home passes; preparation remains counted |
| New GPU ready before Home | No wait (evidenced) | 45 / 61 | Launch 0–40; blocks 0–40 | 61 / 16 | 61 | Run exception (21 non-launch seconds); post-Home misses |
| Home completes during launch | No wait (evidenced) | 10 / 55 | Launch 0–45; blocks 10–45 after Home | 55 / 45 | 55 | Exceptions (Run: 20 non-launch seconds; post-Home: 10) |
| Overlapping queue/GPU wait; no Home necessary | 0–40 | Robot-ready at admission 40 / 85 | Launch/blocks 0–50; shares 40 queue seconds | 85 / 45 | 45 | Both miss: Run 85−40−50+40=35; post-Home 45−10=35. Overlap cannot be subtracted twice |
| Warm GPU, slow coding | No wait (evidenced) | 5 / 35 | None; GPU already available | 35 / 30 | 35 | Both miss; coding is no automatic exemption |
| No Home needed; robot already admitted/ready at Run | Already admitted (evidenced) | 0 / 14 | None | 14 / 14 | 14 | Both pass; readiness evidence fixes the boundary at Run |

Reinstalling preserves an existing checklist, including its evidence and checked
states; it does not automatically migrate old timing text. Review the updated
canonical timing requirements and deliberately reconcile the maintained
requirements, procedures and evidence fields in each integration copy. Preserve
historical measurements and assessments as dated evidence, identify their old
contract, and leave new or unverified requirements unchecked. An old pass or
backend packet timestamp alone cannot qualify either new motion measure.
The repository's maintained RoboSkills copies follow this preservation pattern.

## Prevent command-contract failures

[CONTROL-CONTRACT.md](CONTROL-CONTRACT.md) is required before physical runs and
completion. It requires tests for every advertised primitive through the actual
packet generator, serializer and deployed validator, including real fractional
starting states and exact endpoints. Valid gripper-close=0 must not become a
negative interpolation residual; invalid requested values must still fail.
Validate before dispatch and distinguish local validation errors from physical
workspace/contact stops. Retain each failure as a reproducible regression.

The integration must run those tests in a required CI check or deployment
preflight and retain command/output/revision evidence. The installer distributes
and verifies the requirements; it does not execute arbitrary adapter tests or
certify physical success. A joint-motion smoke test cannot establish complete
pick-and-place. Task outcomes and the current completion proportion must reopen
affected requirements after a relevant failure or changed control code.

Existing integrations must reinstall from the shared source to receive the
independently managed control contract and startup loading rule. Their working
checklist and earlier evidence remain intact; deliberately add/reconcile the new
requirements as unchecked until verified. `install --check` detects a legacy
installation missing the new contract. Edited managed control requirements are
preserved with an actionable failure; scope rendering refuses a missing or
changed control contract. This verifies instruction setup, not passing tests or
new authorization. Do not change global approval settings or hardware limits.

## Verify the portable setup

```sh
python -m unittest discover -s codex-runner/integration-harness/tests -v
```

The tests use disposable directories and synthetic consent references. They
exercise evidence preservation, idempotence, dry-run/check behavior, edited-file
protection, symlink/path refusal, and standalone review-context rendering. They
send no robot commands or identity data and change no approval settings.

