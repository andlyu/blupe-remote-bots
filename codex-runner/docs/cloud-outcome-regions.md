# Cloud outcome regions

The Cloud view's **Highlight** selector adds a descriptive overlay for areas
with more Success or Failure labels. **Success & failure areas** is the default;
the other choices are **Success-heavy areas**, **Failure-heavy areas** and
**None**. The browser remembers the choice under `yam-cloud-highlight`. None
removes the overlay while keeping individual run colors visible.

The overlay uses the existing green Success (`#246744`) and red Failure
(`#b2352c`) colors as translucent tints behind the run markers. Selected areas
may also show a count label such as `Success: 6/8`: six Success labels among
eight nearby Success/Failure labels. These are local descriptive counts, not a
confidence estimate, statistical test or new model score. Both Success and
Failure count labels show a representative task prompt from their matching
outcome beneath the count when one is available.

## Automatic neighborhood rules

[`regionsFor` in `../static/task-cloud.js`](../static/task-cloud.js) applies these
rules to runs with exactly three finite persisted `xyz` coordinates:

1. Group runs at identical coordinates, retaining the number of individual
   attempts in each outcome. Repeated attempts count separately; grouping only
   avoids repeating the same position search.
2. At each occupied position, count runs within a Euclidean radius of `0.08` in
   the saved 3D coordinate system, including the boundary and the center itself.
   Screen position, camera rotation, zoom and the small display offsets used to
   separate repeated attempts do not affect these counts.
3. A candidate center must itself have a Success or Failure label. Its
   neighborhood must contain at least five Success/Failure labels, with at
   least two-thirds of them sharing one outcome. Exactly two-thirds qualifies.
   Uncertain and Unscored runs do not enter that denominator or establish a
   candidate center, but their separate nearby counts are retained.
4. Rank candidates by the absolute difference between Success and Failure
   counts, then by the binary-label total, then by the coordinate key for a
   deterministic tie break. Keep at most 12 areas for each outcome. Centers
   with the same outcome must be at least `0.12` apart (`1.5 × 0.08`); centers
   with different outcomes may be closer.

Automatic region selection is a compact summary rather than a partition of the
cloud. Neighborhoods can overlap, one run can support multiple areas, and spacing or
the per-outcome cap can suppress qualifying candidates. A missing tint does not
mean no nearby Success or Failure labels exist. For count labels, the renderer
considers the two strongest regions per outcome in combined mode when the canvas
is narrower than `600px`, and three per outcome otherwise. Single-outcome mode
considers the six strongest regions. Offscreen centers are skipped, and labels
are omitted if no bounded, collision-free placement is available. The tint fades
beyond the analysis radius to `1.4` times its projected size; its soft edge is not a membership boundary.

## Median outcome prompts

Each selected Success or Failure region receives a `representativePrompt` from
runs with that same outcome inside its inclusive `0.08` neighborhood in persisted
3D coordinates. For each coordinate axis, take the median across individual
matching attempts; repeated attempts carry equal weight, and an even-sized set
uses the average of its two middle values. Matching runs with blank prompts still
contribute to this coordinatewise median.

Choose the actual nonblank matching prompt whose run coordinates are nearest to
that median by Euclidean distance. Ties are resolved by the combined robot and
episode key, then prompt text using the implementation's string comparison. The displayed
value is trimmed. If no matching run has a nonblank prompt, it is empty and the
label remains count-only. This is an observed task prompt, not a generated
summary or a median of words. Success captions use successful attempts, Failure
captions use failed attempts, and neither uses Uncertain or Unscored attempts.

The canvas keeps the count above up to two prompt lines. Prompt text wraps at
word boundaries and is ellipsized when needed, with a text-width limit of
`210px` or the available canvas width minus `30px`, whichever is smaller. Label
height grows by `16px` per prompt line from the existing `24px` count label.
Collision checks use those variable heights for both area labels and individual
run labels. Each area caption tries vertical offsets in order `0, +1, -1, +2,
-2, +3, -3`, multiplied by its height plus `10px`, from the usual position above
the region center. Each candidate is clamped within the canvas and checked
against placed labels. A caption moved to an alternate position has a `1px`
connector in its outcome color back to the region center. These placement rules
do not alter the 3D analysis, outcome counts, region ranking or median prompt;
the existing offscreen checks, colors and interactions remain in effect.

## Select an arbitrary area

**Select area** switches the canvas from rotating/opening runs to drawing a
selection box. Drag over point centers and release to apply; the box includes
centers at all depths, including overlapping points, using the current projected
positions and display offsets. It is a screen-space selection, not a 3D volume
or an automatic neighborhood. In selection mode, arrow keys start or move a box,
Shift+arrows resize it,
and Enter applies it. Escape cancels an in-progress box; with no box being drawn,
Escape leaves selection mode. **Clear selection** removes the selected set.

The summary reports total selected runs and separate Success, Failure, Uncertain
and unlabeled or excluded counts. Its success rate is `Success / (Success +
Failure)` under the current Auto/Human label source; Uncertain and Unscored runs
are excluded from that denominator. Empty selections and selections with no
Success/Failure labels explicitly say that a rate is unavailable.

**Median prompt** chooses an actual prompt nearest the coordinatewise median,
as the automatic captions do, but includes every selected mapped attempt across
all outcomes. It is not restricted to the successful or failed subset. A blank
prompt contributes coordinates but cannot be the displayed representative; when
no selected prompt is available, the summary says so.

Applied membership is retained by the combined robot and episode key. Camera rotation, zoom,
reset and resizing remove the old screen box while preserving membership and
dimming unselected points. Changing label source recomputes counts without
changing membership. Catalog/model/search changes prune runs that are no longer
mapped in the current catalog; switching to another robot clears selection.
Selection and summaries stay in memory and do not load more runs, write labels
or issue robot commands. Leaving selection mode restores the usual camera,
preview and replay interactions while retaining the applied set.

## Label source, robot and filter scope

The overlay analyzes the current Cloud catalog supplied by
[`../static/hosted.js`](../static/hosted.js), after the selected robot, model and
search filters. It uses only mapped runs in that catalog. If the server limits
the displayed catalog, the areas summarize that displayed subset, not every
archived run or the full population used by existing model score calculations.
Runs without valid coordinates do not contribute.

Every supplied run carries the current **Labels** selection, and regions use
the same outcome resolver as individual markers. **Auto-labeled** uses the
matching prediction only. **Human-labeled** follows the saved-runner, imported
human-review and community precedence described in
[`cloud-label-sources.md`](cloud-label-sources.md). Missing auto labels do not
borrow human labels. Annotation lookup uses both robot and episode identifiers.
Changing label source or catalog filters invalidates the previous analysis and
recalculates the areas; source changes do not alter the saved labels or map
coordinates. The standalone cloud component's legacy fallback, when the label
resolver is absent, recognizes only included runner Success/Failure labels.

## Counts and interaction

The status text reports how many success-heavy and failure-heavy areas pass the
current selection, explains the five-label/two-thirds rule, and explains when
none qualify or highlights are off. With highlights enabled, it also explains
that area labels include a median task prompt. It is a `role="status"`
paragraph associated with the canvas through `aria-describedby`.

With highlights enabled, hovering or focusing any mapped run adds its nearby
Success, Failure, Uncertain and Unscored counts to the existing textual run
description, even when its neighborhood does not qualify for a tint. Uncertain
and Unscored counts are explicitly described as excluded from the binary
denominator. When the run is within a Success or Failure area visible under the
current highlight selection and that area has a representative prompt, the
description also includes the full **Median success prompt** or **Median failure
prompt**. If several such areas contain the run, it uses the nearest area
center. This supports inspection without relying on tint color or the limited canvas labels. Table remains the accessible
alternative for run browsing. Highlight choices do not change point selection, replay opening,
preview behavior, rotation or zoom.

## Performance and interpretation limits

Identical-coordinate aggregation and a spatial hash with `0.08` cells restrict
each neighborhood search to its own cell and the 26 adjacent cells. The analysis
is cached until the supplied run set changes; camera movement only reprojects
the selected areas. Switching highlight mode reuses the analysis. This avoids
an unconditional pairwise search over all attempts, but a densely packed set of
many distinct positions can still require quadratic work. Selecting a median
prompt additionally scans the supplied runs for each retained outcome region
(at most 12 per outcome) and sorts that region's matching attempts. Applying an
arbitrary selection filters projected point centers, then sorts the selected
mapped attempts for its median prompt. No browser timing or
large-catalog performance result is claimed by this documentation review.

The map expresses similarity between task descriptions. Nearby points do not
establish identical starting conditions, physical difficulty or causal effects.
The fixed radius and thresholds are display heuristics, not learned clusters or
validated significance boundaries. Counts inherit the chosen source's coverage,
label errors and selection bias; auto predictions remain predictions. Use the
individual run descriptions and replay evidence when interpreting an area.

## Design conformance evidence

This is a narrow Operate extension of the incumbent playground's canvas and
native controls. This documentation pass inspected the uncommitted changes in
`static/task-cloud.js`, `static/hosted.html`, `static/hosted.css`,
`static/hosted.js` and `tests/test_task_cloud_ui.cjs`. Automatic labels retain the
stronger count above regular-weight prompt text, paper background and existing
outcome colors. The selection toggle has pressed and focus states; visible help
explains keyboard controls and depth inclusion. Counts use a polite status
region, and the full summary is associated with the focusable canvas.

**Verdict: conforms at the inspected source scope.** The test definitions cover
all-outcome selected-area medians, separate unknown counts and binary-label
rates, pointer and keyboard selection, cancellation, retained membership under
camera/source changes, filter pruning, robot clearing, empty states, and both
Success and Failure captions. Existing caption tests cover stable median choice,
blank fallback, rendering and bounded two-line text. The added combined-mode
`320 × 360` canvas regression checks that both Success and Failure captions are
drawn when their default positions collide, that label boxes remain within the
canvas, and that region and run counts are preserved. This documentation pass
executed no tests, browser, backend, network or hardware action. It makes no
rendered-layout, screen-reader, playback or measured-performance claim; those
require the parent task's verification. No product or design-system file was
created or modified by this pass.
