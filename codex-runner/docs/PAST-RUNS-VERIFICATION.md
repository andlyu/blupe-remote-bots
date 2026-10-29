# Past Runs implementation verification

Baseline: public repository commit `224bd14`. Verified October 28, 2026.

## Automated checks

- Python: 97 tests passed in 1.872s. Command:
  `PYTHONPATH=codex-runner/src:codex-runner/tests python3 -m unittest test_hosted test_run_assessments test_task_cloud test_run_assessment_hosted test_past_runs test_run_search test_run_model_filter test_run_model_filter_hosted test_run_search_hosted test_replay_link_hosted test_history_endpoint test_quick_replay_proxy test_past_runs_video_layout`.
- JavaScript: `node --test codex-runner/tests/*.cjs`; 334 passed, including live
  labels, five-second timing/concurrent preview request, processing/error handling,
  edit/review controls, search explanations, pagination/filter races, multiple
  models, view preference/selection, xyz rotation, duplicates, and empty focus.
- API truth tests cover 0/0, positive/tied/negative majorities, changing/removing
  votes, duplicate and concurrent submissions, stale label revisions, wrong owner,
  originating-session review rejection, later same-session/same-recorded-user
  edits, fresh current votes with retained prior history, and provisional labels.
- Catalog tests exercise 10,005 records with a 10,000-point display cap. Scores
  include all filtered records before either display cap or table pagination.
  Metadata listing never fetches episode detail/media. Empty groups return null
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
hardware control prevented physical operation. The available archive yielded 552
visible runs after incumbent archive exclusions and the selected robot scope.

Checked desktop and a real 390px iframe viewport: readable Table rows and columns,
Your runs above All runs, Cloud keyboard rotation/zoom/reset, pointer controls,
per-attempt cycling/open, shared replay selection, vote exclusion without label
flipping, vote change/removal restoring inclusion, and selected-row retention.
An own-run fixture showed all three live controls and saved a provisional label.
Termination opened an indeterminate processing review; the runner changed the
label afterward and both revisions remained in history. Exact five-second timing
and immediate overlapping receipt fetch were checked with controlled JS timers.
The recorder/V0 pipeline itself is unchanged; no new physical recording was made.

Visual inspection found and fixed long table rows, selected-button hover contrast,
a `data-camera` collision with the existing camera renderer, stale Cloud focus
after filters, and a live-footer grid placement issue. A separate Impeccable
reviewer scored the focus and live-layout corrections resolved, disposition ship
at that fix-list scope. A separate documenter confirmed the incumbent system was
preserved. Detector findings in unrelated pre-existing camera/legacy CSS were
kept out of this scoped change.

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
