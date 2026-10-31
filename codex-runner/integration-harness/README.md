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
contract into `docs/BLUPE-HARNESS-CONTRACT.md`. Existing instructions and completed
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
Stop and normal release proceed without repeated confirmation. The pre-test notice is progress,
not a new permission question. Keep all normal queue/lease, readiness, command
validation, hardware limits and Stop checks. Never retry a timed-out movement.

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
Do not use an Automated identity to evade a restriction. Explicit tool or managed
denials remain binding: retain the exact action/reason and continue independent
work or a materially safer alternative. A documentation/install update does not
authorize retrying the denied action through another route.

No global Codex configuration, reviewer policy, robot service, or credentials are
changed by installation or rendering. Automatic review acceptance cannot be
guaranteed by repository text. Complete the physical/replay/timing checklist with
deployed evidence before declaring the integration finished.

## Timing contract and existing integrations

For every ordinary run, verify first observed method-driven physical motion
within **15 seconds after matched settled startup Home completion** and
**30 seconds after Run**. If Home is unnecessary, document the earliest per-run
robot-ready boundary as specified in the checklist; do not wait for model/code
readiness to start that clock. Home/preparation motion does not count. Site-entry
timing is contextual evidence. Keep both full elapsed times and timed visual
proof, with matched Home/readiness lifecycle evidence.

A genuinely new GPU launch must be visible inline for its entire real
start-to-ready interval. Keep full elapsed times and label a target miss caused
by evidenced GPU-launch blocking time as an exception. Only that blocking
overlap may be excused from each clock under the checklist's limits. Warm GPUs,
queueing, coding and model loading receive no automatic exception. GPU ready
before Home leaves the full 15-second post-Home limit intact.

These illustrative timelines use seconds after Run and assume complete visual,
Home/readiness and (where applicable) persistent UI/lifecycle evidence. They are
worked examples, not physical verification:

| Scenario | Home / motion | GPU launch and actual blocking | Full Run / post-Home seconds | Outcome |
| --- | --- | --- | --- | --- |
| Ordinary run | 12 / 26 | None | 26 / 14 | Both pass |
| Queue delay | 40 / 45 | None | 45 / 5 | Run misses; post-Home passes |
| New GPU ready before Home | 45 / 61 | Launch 0–40; blocks 0–40 | 61 / 16 | Run exception (21 non-launch seconds); post-Home misses |
| Home completes during launch | 10 / 55 | Launch 0–45; blocks 10–45 after Home | 55 / 45 | Exceptions (Run: 20 non-launch seconds; post-Home: 10), never normal pass |
| Warm GPU, slow coding | 5 / 35 | None; GPU already available | 35 / 30 | Both miss; coding is no automatic exemption |
| No Home needed; robot already admitted/ready at Run | 0 / 14 | None | 14 / 14 | Both pass; readiness evidence fixes the boundary at Run |

Reinstalling preserves an existing checklist, including its evidence and checked
states; it does not automatically migrate old timing text. Review the updated
canonical timing requirements and deliberately reconcile the maintained
requirements, procedures and evidence fields in each integration copy. Preserve
historical measurements and assessments as dated evidence, identify their old
contract, and leave new or unverified requirements unchecked. An old pass or
backend packet timestamp alone cannot qualify either new motion measure.
The repository's maintained RoboSkills copies follow this preservation pattern.

## Verify the portable setup

```sh
python -m unittest discover -s codex-runner/integration-harness/tests -v
```

The tests use disposable directories and synthetic consent references. They
exercise evidence preservation, idempotence, dry-run/check behavior, edited-file
protection, symlink/path refusal, and standalone review-context rendering. They
send no robot commands or identity data and change no approval settings.
