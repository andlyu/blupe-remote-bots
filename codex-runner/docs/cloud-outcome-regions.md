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

## Select a 3D volume

**Add 3D box** immediately creates a finite box in map space and opens an angled
camera view. Its center is the coordinatewise median of mapped attempts; its
half extents use half the20th–80th-percentile span of each coordinate, bounded
to `0.08–0.3`. Initial axes match the saved map axes. This gives the same initial
membership on desktop and phone, independently of the viewport. Adding a box
focuses and scrolls to the canvas; **Reset 3D box** starts over from the current
filtered catalog. **Redraw footprint** optionally replaces it using a drawn
outline at the median candidate depth, as in the earlier selection flow.

The toolbar adopts the familiar interaction patterns in
[Three.js TransformControls](https://threejs.org/examples/misc_controls_transform.html),
[Potree clipping volumes](https://potree.org/potree/examples/clipping_volume.html)
and [CloudCompare section boxes](https://www.cloudcompare.org/doc/wiki/index.php/Cross_Section).
The implementation uses the existing perspective renderer; these are pattern
references, not a new runtime dependency or copied upstream source. See the
[reference notes](refs/task-cloud/selection-controls.md).

- **Move box** shows arrows along its local X/Y/Z axes. Dragging an arrow moves
  the entire volume along that axis, without moving the camera or changing size.
- **Resize box** shows six face handles. Dragging one moves that boundary and
  its center while keeping the opposite face fixed. Width/height/depth range
  controls below the canvas also support symmetric resizing about the center,
  from `5%` to `300%` of the initial dimensions.
- **Rotate box** shows three projected rings. Dragging a ring rotates the box
  about its own corresponding axis; center and size stay fixed. The pointer ray
  intersects the ring's actual3D plane, and Rodrigues rotation updates the
  orthonormal basis. Move/resize use a ray plane containing the selected axis.

Red X, green Y and blue Z identify box controls, separately from run-outcome
colors. Active tools use a pressed state. With the canvas focused, W selects
Move, R Resize and E Rotate. Native X−/X+/Y−/Y+/Z−/Z+ buttons provide keyboard
and touch-friendly alternatives: move10% of box size, resize10%, or rotate15°.
Escape and pointer cancellation restore a transform being dragged. Pinching
cancels an unfinished outline and zooms without applying it.

Dragging empty space or using arrow keys orbits the camera while retaining the
box in map space. **3D**, **Front**, **Top** and **Side** are camera presets;
camera orientation, zoom/reset and responsive resizing do not alter selection.
**Depth position** translates along the current box Z axis. **Clear selection**
removes the volume. Hover/focus video previews pause while a box is present so
they do not obscure it; clicking a run still opens its replay. Clearing restores
ordinary previews and automatic region/task captions.

Membership tests all six faces against the original, unjittered saved `xyz`,
including boundaries. Screen-overlapping runs outside the box's depth are
excluded; repeated attempts retain equal weight. Invalid/unmapped runs do not
contribute. Source/filter/catalog changes recalculate counts within the same
volume; changing robots clears it. The box and summaries remain memory-only.

The bounded label beside the projected box shows run count, success percentage,
Success/Failure denominator, uncertain/unknown coverage, and an ellipsized actual
median prompt. Full accessible counts and median stay below the canvas, masked
from analytics. Percentage is `Success / (Success + Failure)` under the selected
Auto/Human source; empty/no-binary-label selections have no success percentage.
Median prompt is the actual task nearest the coordinatewise median across all
selected mapped outcomes. This is a descriptive result for the selected volume.

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
(at most 12 per outcome) and sorts that region's matching attempts. Applying or resizing a
volume tests persisted coordinates against its three orthonormal axes and six
faces, then sorts selected mapped attempts for the median prompt. No browser timing or
large-catalog performance result is claimed by this documentation review.

The map expresses similarity between task descriptions. Nearby points do not
establish identical starting conditions, physical difficulty or causal effects.
The fixed radius and thresholds are display heuristics, not learned clusters or
validated significance boundaries. Counts inherit the chosen source's coverage,
label errors and selection bias; auto predictions remain predictions. Use the
individual run descriptions and replay evidence when interpreting an area.

## Design conformance evidence

The3D selection follows the incumbent Operate canvas, paper background,
native controls, palette and focus treatment. Axis arrows, face handles and rotation rings use
the same projection as all twelve box edges. A neutral label attached to the
box keeps counts distinct from outcome colors; dashed far edges convey depth.
Full counts and median remain in accessible DOM text, with two-column controls
at phone widths. Geometry tests cover six-face boundaries, screen-overlapping
runs at distinct depths, stable box membership under camera/source changes,
dimension and depth-position changes, one-face resize, move and true plane-based
rotation, transform cancellation and robot reset.
Rendered desktop/phone and deployed evidence are recorded in the task checklist.
