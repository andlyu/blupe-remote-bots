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
confidence estimate, statistical test or new model score.

## Neighborhood and selection rules

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

Area selection is a compact summary rather than a partition of the cloud.
Neighborhoods can overlap, one run can support multiple areas, and spacing or
the per-outcome cap can suppress qualifying candidates. A missing tint does not
mean no nearby Success or Failure labels exist. For count labels, the renderer
considers the three strongest regions per outcome in the combined mode, or the
six strongest regions in a single-outcome mode, before skipping
offscreen centers and colliding labels. The tint fades beyond the analysis radius to
`1.4` times its projected size; its soft edge is not a membership boundary.

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
none qualify or highlights are off. It is a `role="status"` paragraph associated
with the canvas through `aria-describedby`.

With highlights enabled, hovering or focusing any mapped run adds its nearby
Success, Failure, Uncertain and Unscored counts to the existing textual run
description, even when its neighborhood does not qualify for a tint. Uncertain
and Unscored counts are explicitly described as excluded from the binary
denominator. This supports inspection without relying on tint color or the
limited canvas labels. Table remains the accessible alternative for run
browsing. Highlight choices do not change point selection, replay opening,
preview behavior, rotation or zoom.

## Performance and interpretation limits

Identical-coordinate aggregation and a spatial hash with `0.08` cells restrict
each neighborhood search to its own cell and the 26 adjacent cells. The analysis
is cached until the supplied run set changes; camera movement only reprojects
the selected areas. Switching highlight mode reuses the analysis. This avoids
an unconditional pairwise search over all attempts, but a densely packed set of
many distinct positions can still require quadratic work. No browser timing or
large-catalog performance result is claimed by this documentation review.

The map expresses similarity between task descriptions. Nearby points do not
establish identical starting conditions, physical difficulty or causal effects.
The fixed radius and thresholds are display heuristics, not learned clusters or
validated significance boundaries. Counts inherit the chosen source's coverage,
label errors and selection bias; auto predictions remain predictions. Use the
individual run descriptions and replay evidence when interpreting an area.

## Design conformance evidence

This is a narrow Operate extension of the incumbent playground. Source review
covered `task-cloud.js`, `hosted.js`, `hosted.html` and `hosted.css`, together with
the existing label-source documentation. The labeled native select extends the
wrapping Cloud toolbar, inherits the existing form styling and focus treatment,
and uses the existing help-text scale. The overlay preserves the paper canvas,
individual green/red/amber/hollow markers and the established run controls.
Written counts, the status paragraph and the focused-run description accompany
color. No new visual system or design-system files are introduced.

**Verdict: conforms at the inspected source scope.** This documentation pass did
not run a browser, backend service, network request or hardware action. It makes
no claim about rendered layout, responsive behavior, screen-reader output or
measured interaction performance; those require the parent task's finish
verification. No root `PRODUCT.md`, `DESIGN.md` or `.impeccable/design.json` was
present. The nested RoboSkills site's design files describe another surface.
