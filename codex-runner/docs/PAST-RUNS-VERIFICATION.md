# Past Runs implementation verification

Started from `224bd14`; incorporated current main `a2f3383` before final checks. Verified October 28, 2026.

## Automated checks

- Python: 107 tests passed in 2.100s. Command:
  `PYTHONPATH=codex-runner/src:codex-runner/tests python3 -m unittest test_hosted test_model_catalog test_run_assessments test_task_cloud test_run_assessment_hosted test_past_runs test_run_search test_run_model_filter test_run_model_filter_hosted test_run_search_hosted test_replay_link_hosted test_history_endpoint test_quick_replay_proxy test_past_runs_video_layout`.
- JavaScript: `node --test codex-runner/tests/*.cjs`; 338 passed, including live
  labels, five-second timing/concurrent preview request, processing/error handling,
  edit/review controls, search explanations, pagination/filter races, multiple
  models, view preference/selection, xyz rotation, duplicates, and empty focus.
- API truth tests cover 0/0, positive/tied/negative majorities, changing/removing
  votes, duplicate and concurrent submissions, stale label revisions, wrong owner,
  originating-session review rejection, later same-session/same-recorded-user
  edits, fresh current votes with retained prior history, and provisional labels.
- Catalog tests exercise 10,005 records with a 10,000-point display cap. Scores
  include all filtered records before either display cap or table pagination.
  Cloud metadata listing never fetches episode detail/media; Table fetches detail
  for only its 12 visible preview blocks. Empty groups return null
  rates and No scored runs. Machine Success never backfills a human label.
- Canvas test renders 10,000 supplied attempts in about 48ms in a Node mock
  drawing context. This is a computation check, not a browser frame-rate claim.
- `git diff --check` passed.

## Real representation check

Downloaded the pinned public MiniLM model without an account token. Cold
load/download took 57.727s in the temporary validation environment. Warm model
load plus embedding/projection for 602 public archive records (243 unique
normalized descriptions) took 0.759s. The frozen basis is bundled with a
content-derived version. New-record/filter/vote tests preserve prior xyz values.

Representative real-task inspection: “Eat the apple” is nearest in the 3D map to
“Pick the apple and drop on the plate”, “move the apple out of the plate”, and
“Pick up apple and drop it on the plate”. “Stack the two block” lies near other
block manipulation prompts including swaps and lifting. This is a broad semantic
map, not an action-equivalence or difficulty classifier; PCA3 can lose local
neighborhood detail. Long prompts follow the encoder's documented truncation.

## Browser interaction evidence

Local ASGI fixtures used the real public task text and coordinates with explicitly
synthetic models, human labels and review sessions. Mock session APIs and disabled
hardware control prevented physical operation. The initial fixture showed 552
visible runs including one synthetic replay. The correction comparison removes
that extra replay and shows 551 archive runs after incumbent exclusions and the
selected robot scope.

Checked desktop and a real 390px iframe viewport: incumbent recording blocks and previews,
Your runs above All runs, Cloud keyboard rotation/zoom/reset, pointer controls,
per-attempt cycling/open, shared replay selection, vote exclusion without label
flipping, vote change/removal restoring inclusion, and selected-row retention.
An own-run fixture showed all three live controls and saved a provisional label.
Termination opened an indeterminate processing review; the runner changed the
label afterward and both revisions remained in history. Exact five-second timing
and immediate overlapping receipt fetch were checked with controlled JS timers.
The recorder/V0 pipeline itself is unchanged; no new physical recording was made.

The user rejected the initial dense metadata-table interpretation. Their clarified
Table presentation restores the actual pre-feature recording-block renderer and
CSS from `a2f3383`, rather than restyling rows. The corrected comparison uses the
incumbent rendered blocks as authority: same video geometry, typography, spacing,
two-line prompt, Show reason and live-speed actions, with one small assessment
line. Your runs remains above All runs, with Table/Cloud inside All runs and no
third Cards mode. This user correction supersedes the earlier dense-table design
pass. Verification of the correction includes desktop/mobile incumbent comparison,
exclusive muted hover/focus previews, reduced-motion suppression, reason/details,
search explanations, replay/live speed, filter/pagination races and retained
Cloud selection. The original assessment/scoring/projection semantics are kept.
An independent review of the corrected source and incumbent/current desktop and
mobile captures returned ship with no material fixes. Documentation recheck
confirmed the incumbent palette, typography and block behavior are preserved;
this correction introduces no new design system.

## Integration boundary

The shared code is ready for review. Hosted account ownership is supplied in a
separate application PR; the coordinator reports its isolated ownership validation
passed. That integration does not advance the submodule or deploy and also depends
on publication of the existing account-login integration. Guest/session ownership
already works in the shared runner. An earlier read-only check in the incumbent
private checkout reported “Shared checkout differs from the pin. Test and stage
its version bump explicitly.” This shared task changed no private checkout,
production data, deployment, or submodule pin. Advance only to a published,
reviewed shared commit, install updated requirements, persist/prewarm the index,
and rerun private ownership and hosted integration checks in the integration
checkout. Do not duplicate the existing hosted account adapter.
