# Cloud label sources

The public playground's **Labels** selector beside Table / Cloud switches between
**Auto-labeled** and **Human-labeled** without changing a run's saved assessment.
Auto-labeled is the default; the browser remembers the choice under
`yam-run-label-source`. The selected source applies to cloud markers, accessible
point descriptions, table notes and the visible source totals. Existing model
success-rate calculations remain based on runner assessments; they are hidden in
Auto-labeled mode rather than presented as model-prediction statistics.

## Public snapshot and provenance

[`../annotations/run-labels.json`](../annotations/run-labels.json) is a version-1
public annotation snapshot dated 2026-10-31. It contains 416 Gemini 3.8 Flash
predictions (`gemini-3.8-flash`): 125 Success, 259 Failure and 32 Uncertain. Ten
records also contain actual human trial reviews: four Success, five Failure and
one Uncertain. A prediction is never counted as a human review.

Rows are keyed by `(robot_id, episode_id)`. Each `auto_assessment` retains its
label, model, confidence, reason, timestamped video observations, limitations,
rubric version and source-video SHA-256. The rubric is
`v2-controlled-lift-and-open-ended-uncertainty`: a clear controlled lift satisfies
“pick up” even if the object is later released; tasks without a measurable goal
may be Uncertain. A non-null `human_review` contains only its label and review
timestamp. The snapshot exports no credentials, tokens, private contacts,
reviewer identities or provider billing data. Inspection found no email-like
strings or credential/contact field names, and all 416 video digests have the
SHA-256 format.

`GET /api/run-labels` serves this JSON snapshot through a read-only route in
[`../playground.py`](../playground.py). It does not write runner assessments or
community revision votes. The export is separate from those databases. If the
file is absent, the route returns an empty version-1 payload. The browser fetches
without HTTP caching, validates the version and label vocabulary, and maps rows
by both identifiers. Unknown runs stay unlabeled. A failed load displays an
inline explanation and can be retried with Refresh; runner labels and community
votes continue to work.

## Source precedence and replay evidence

Auto-labeled uses only the matching `auto_assessment`; it never falls back to a
human label. Human-labeled applies this order:

1. A saved runner label wins, subject to its existing `included` eligibility.
   An excluded or invalid runner label remains unscored; it does not fall through.
2. An explicitly unfinished run (`ended: false`) remains unscored.
3. Otherwise use the imported human trial review, then community consensus.
4. Without an applicable label, display Unscored.

The replay's native disclosure shows the prediction, model, confidence, rubric,
reason, observations and limitations, plus the separate human trial review when
present. Text is inserted with `textContent`. Prediction evidence is explicitly
described as separate from the human assessment.

## Updating the snapshot

- Publish only the narrow public schema above. Keep private source databases,
  contacts, credentials, raw reviewer identity and billing metadata out of it.
- Preserve both robot and episode keys, reject duplicate pairs, and retain the
  video digest and rubric/model provenance for each prediction.
- Preserve actual manual reviews as `human_review`; use `null` where none exists.
  Never manufacture a human review from a prediction or write either imported
  source into runner assessments or vote history.
- Keep the `Success`, `Failure`, `Uncertain` vocabulary and version-1 contract in
  sync with `static/run-labels.js`. Human-only rows or a different schema require
  a deliberate loader/schema change; the current loader requires an auto label.
- Recheck source precedence, unavailable/retry behavior, counts, privacy and
  robot scoping using `tests/test_run_labels_ui.cjs`, plus the route checks in
  `tests/test_hosted.py`. Update the counts above when the snapshot changes.
- Deploy the JSON and its reader together. A successful load is retained for
  the page session; reload the page to fetch an updated snapshot. A failed load
  can retry through Refresh. Changing the selector alone does not refetch it.

## Design conformance evidence

This is a narrow Operate extension of the existing quiet green console. Review
covered `static/hosted.html`, `hosted.css`, `hosted.js`, `task-cloud.js` and
`run-labels.js`. The implementation retains the incumbent layout, Manrope font
stack, paper/surface/ink tokens, native form control styling, focus treatment,
Table / Cloud buttons and wrapping toolbar. A labeled native `select` adds the
two source choices; no new component library or page structure is introduced.

The existing Success green (`#246744`), Failure red (`#b2352c`) and hollow
Unscored marker (`#607064` stroke, `#f8faf5` canvas fill) are preserved. Uncertain
adds amber (`#946000`) consistently to the canvas and legend. Written labels,
source totals and accessible point descriptions accompany color. Replay evidence
uses a native `details`/`summary` disclosure and the incumbent text scale.

**Verdict: conforms at the inspected source scope.** Rendered layout, interaction
and responsive verification belong to the parent task's finish review; this
documentation pass ran no browser, backend service, network or hardware action.
No root `PRODUCT.md`, `DESIGN.md` or `.impeccable/design.json` was present to
compare against. The nested RoboSkills site's design documents are a different
surface and were not treated as this playground's system.

Pre-existing drift is reported without repair: `hosted.css` contains accumulated
overrides, including a mobile `runScores p` selector missing its class dot.
This extension does not change it. No design-system files were created or
modified for this ordinary extension.
