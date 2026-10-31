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
arms, approach, task, duration, movement, recording destination, and the actual
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

## Verify the portable setup

```sh
python -m unittest discover -s codex-runner/integration-harness/tests -v
```

The tests use disposable directories and synthetic consent references. They
exercise evidence preservation, idempotence, dry-run/check behavior, edited-file
protection, symlink/path refusal, and standalone review-context rendering. They
send no robot commands or identity data and change no approval settings.
