# Past Runs assessments and task cloud

The shared local and hosted playground uses a durable SQLite overlay keyed to the
public archive's canonical `ep_…` IDs. The archive remains evidence; its machine
ending/completion/error metadata does not supply human assessments.

## Assessment API

`POST /api/run-assessment` uses the existing browser session cookie, same-origin
JSON policy and `X-YAM-Runner-Token`. It accepts `episode_id` and an `operation`:

- `read` (default): returns label/revision, correct/incorrect counts, eligibility,
  `can_edit`, `can_vote`, this session's vote, and revision history.
- `assess`: accepts `label` (`Success`, `Failure`, or null for Not completed) and
  the last read `revision`. Only the originating session or its recorded user
  may edit. Identical retries do not create new revisions.
- `vote`: accepts current `revision` and `vote` (1 correct, -1 incorrect, null
  remove). Each reviewer session has one current vote. The originating session
  cannot vote on its own label. Stale revisions return 409.

Ended labeled runs count with `correct >= incorrect`, including 0/0. A negative
majority excludes the run without changing its label. Unlabeled and live runs
are unscored. Label changes retain earlier assessments/reviews, starting current
votes at zero. Vote-change/removal events are also retained privately. No session
or account identifiers are returned in public data.

Assessment ownership is captured in maintenance and assessment-read paths, never
as new overlay I/O before Stop. The shared `HostedRunner.assessment_user(visitor)`
hook defaults to `visitor.recorded_user_id` when an application has already set it.
Hosting applications should override this hook with an existing recorded account
identifier. Do not use a supplied email, display name, model session ID, or value
from request JSON. No new sign-in or verification flow is required for labels or
reviews; guests keep session ownership and session-based voting.

## Catalog and UI

`GET /api/run-catalog?robot_id=…&model=…&model=…&q=…&view=table|cloud&offset=…`
returns complete filtered per-model/version scores and Table block pagination or
lightweight Cloud coordinates. Table enriches only its 12 visible recording blocks
with the incumbent preview, machine ending, reason and playback metadata.
Unknown versions stay separate as unknown;
recorded model IDs (including versions in the ID) are never collapsed. Counts
are calculated before pagination and the Cloud's disclosed 10,000-point limit.
Selected models with no matching tasks show No scored runs, not zero percent.
Existing keyword/related-term explanations and relevance ranking remain in Table.
Cloud filters the same matches without changing coordinates.

Your runs retains its own current-session collection above All runs. Table is the
first-visit default; only the chosen Table/Cloud preference is stored in browser
storage. Filter/selection state survives view switches. Table is the user's name
for the familiar recording-block grid, using the original
video previews, two-line task text, hover/focus behavior, reason/details and
live-speed replay actions. A small runner-assessment/review line augments each
block; recorded model version is available in its existing details. Full task
text remains in the accessible replay action and replay. Both views select into
the same replay/processing surface. Cloud fetches recording detail lazily for the
hovered or keyboard-focused point and on full replay selection;
Table retains preview information for only its visible blocks. Blocks remain
keyboard accessible and stack in one column on phones. Cloud supports drag/pinch,
wheel, rotation keys,
zoom/reset buttons, keyboard run cycling, and per-attempt replay access.

Cloud uses dots throughout: eligible Success is filled green, eligible Failure is
filled red, and unscored runs are hollow. Unlabeled and vote-excluded runs share
the hollow treatment and contribute to neither score count. A labeled run regains
its original green/red fill when votes restore eligibility; the label, revisions
and exclusion reasons remain in replay details. Text equivalents and the legend
describe these states, and per-model summaries combine the unscored counts.

A compact preview near the hovered/focused point uses the real recording source,
saved camera layout and existing playback-speed helper. It plays muted and loops;
loading, buffering, blocked playback and unavailable video are explicit. Reduced
motion suppresses autoplay. Only one preview is alive: changing points aborts the
previous detail request and removes its paused media/layout callbacks, and stale
responses cannot replace the current point. Leaving, rotating/zooming, opening
replay, changing filters/views/robot, and hiding the page clear it. Keyboard focus
and Previous/Next support previews; Enter opens replay and Escape dismisses the
preview. Touch interaction retains the existing full replay access.

During a run, the three human assessment controls are visible. Labels are
provisional. At termination the existing recorder begins V0 preparation; the UI
starts checking that receipt immediately while leaving five seconds for assessment.
Then it opens review, explicitly processing if the video is still unavailable.
This timer is not an edit deadline. The same assessment controls remain available
in replay afterward. Existing motion and Stop operations are unchanged.

See [task cloud references](refs/task-cloud/INDEX.md) for the pinned encoder,
bundled frozen PCA basis, indexing cache and operational setup. Failed or offline
indexing leaves an explicit Cloud state and a working Table. The map describes
prompt similarity; rates on different task mixes are not controlled benchmarks.

## Hosted integration handoff

Shared functionality ships in this repository. The private deployment must advance
its submodule only to a published, reviewed shared commit, persist both overlay
and map databases, install updated runner requirements, and prewarm the index.
For recorded-user edits from later sessions, the existing private account adapter
must provide its stable account identity via `assessment_user`. Keep that adapter
in its owning application. Run the private `scripts/check_repo_ownership.py` and
hosted integration tests before landing a private hook or submodule pin. This
shared change does not deploy, merge, or operate a physical robot.
