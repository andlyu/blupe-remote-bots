# Run sidebar

Selecting a Cloud point, table run or similar-video card opens the existing
replay player in a nonmodal sidebar. The active Cloud point and table selection
still use the existing selection path. The selected run keeps its machine ending,
separate auto/human label evidence, playback-speed controls and recorded-camera
view. Post-run replay processing also opens this sidebar. While replay details
load, known model and version values survive null, missing or empty values from
the detail response. A pending replay summary uses the recorded runner name or
the neutral **Run replay** fallback when that name is absent.

## Layout and controls

The native `dialog` uses `show()` with `aria-modal="false"`. Above 900 px it docks
to the right at 450 px wide and full viewport height. Only the Past runs section
narrows and aligns left while it is open; the live controls keep their existing
layout. At 900 px and below it becomes a full-width bottom drawer at 90dvh, with
rounded top corners.

The header and active player occupy separate grid rows above the scrolling body.
The active video is capped at 32dvh on desktop and 28dvh on smaller screens. The
body contains the task, model/ending information, playback controls and **Similar
videos**. Existing runner-assessment, community-review, replay-email and metrics
controls remain available under **Run details and human assessment**, a native
`details` disclosure. The existing **Close and run another** button also lives in
that disclosure; it closes the replay, removes the run link parameter and focuses
the prompt.

Close and Escape dismiss the sidebar. Escape leaves fullscreen playback and
any open native modal dialog, such as email or settings, to their own controls.
The sidebar remembers its opening focus target and restores it on close when that
element still exists. Selecting another run from inside the sidebar moves focus
to **Close** while retaining the original external return target. Related cards
are native buttons with task-based accessible names and a visible focus outline.
Their decorative video previews are excluded from keyboard navigation and the
accessibility tree. Inline status text covers searching, loading previews, empty
suggestions, unavailable previews and retry. A blocked active replay autoplay
attempt shows **Press Play to start this replay.**

## Similar-video selection

The list is scoped to the selected run's robot. It excludes the selected episode,
duplicate episode IDs, rows without a published-video indication, explicit
zero-duration videos and unavailable videos. A published-video indication is a
preview URL, video URL or `original_available: true`; playback availability is
checked again when details load.

Text is NFKC-normalized, lowercased and stripped of punctuation. Task-word
sets omit the built-in list of common filler words, including the directional
words “up” and “down.” Their Jaccard overlap is the number of shared words divided
by the number of distinct words across both prompts.

Candidates qualify under these rules:

- An exact nonempty normalized prompt always qualifies.
- When both runs have finite three-dimensional coordinates, task-word overlap
  must be at least 0.4, or at least 0.2 with Euclidean distance at most 0.2.
- When a coordinate pair is unavailable, task-word overlap must be at least 0.25.

Map proximity alone cannot qualify an unrelated task. Exact prompts rank first,
then greater task-word overlap, shorter three-dimensional distance (missing
coordinates use 1 for this tie-break), newest start time and episode ID. At most
40 suggestions are retained. These are local comparisons of existing metadata;
opening the sidebar makes no model inference call.

The Past runs **Labels** choice supplies the cards' Auto or Human outcome text
through the existing label resolver. It changes displayed label provenance,
without changing similarity membership or writing an assessment. Unscored entries
are explicitly described as **Unlabeled or excluded**. See
[Cloud label sources](cloud-label-sources.md) for precedence and evidence rules.

## Loading and cleanup

A complete unfiltered Cloud catalog can be reused in memory for 60 seconds per
robot. Filtered or sampled history results are not supplied as a complete cache.
When a fresh catalog is needed, the sidebar requests
`GET /api/run-catalog?view=cloud&robot_id=…` with the matching robot header.

Cards append eight at a time. An `IntersectionObserver` rooted in the sidebar's
scrolling body adds the next group near the list end; **Show more similar videos**
provides an explicit alternative. Near-visible cards resolve published video
details through robot-scoped `GET /api/past-runs` requests only when no URL is
already available. The related-preview queue starts at most two detail requests
at once and retains at most six related video sources, separate from the active
player. Preview videos begin with `preload="none"`, then use metadata loading
when given a source. Metadata arrival seeks to the earlier of one second or half
the duration. The card says **Loading preview…** until `loadeddata` or `seeked`,
then **Select to watch**. Offscreen sources are released. Pointer hover can play a
loaded preview unless reduced motion is requested; pointer leave pauses it.

Closing, changing the selected run or changing label source cancels the previous
related-list scope, aborts its requests, disconnects its observers and releases
its media. Responses from an old scope cannot populate the new list. Selecting a
different robot closes an open sidebar. A failed catalog load offers **Retry
similar videos**. Related-list catalog and episode state are memory-only; this
extension adds no persistent history-ID storage, robot command or new write API.
Existing assessment and email actions remain explicit controls.

Without `IntersectionObserver`, the button still appends cards. The first three
suggestions can load immediately; later cards resolve a preview on pointer hover
or keyboard focus and release it on pointer leave or blur. Selecting any card
opens the active replay. Browser playback, network transfer sizes and the
preview-source bound under real scrolling require runtime checks;
`preload="metadata"` is a browser hint, not a byte-budget guarantee.

## Design conformance and verification scope

This is an Operate extension of the incumbent quiet green console. It inherits
Manrope, the console's paper/ink/muted/border tokens and native controls. Task and
section titles use 17 px type; related titles use 14 px and metadata 12 px. A thin
border separates the dock, header and rows; the player uses a dark green video
surface. The responsive drawer and compact rows describe this surface only.

**Source-conformance verdict: conforms within the inspected scope.** Review
covered `static/hosted.html`, `static/hosted.css`, `static/hosted.js`,
`static/replay-history.js`, `static/replay-progress.js` and
`tests/test_run_sidebar_ui.cjs`. The VM tests exercise ranking, robot isolation,
self/unpublished/empty exclusions, rejection of unrelated map-position
collisions, the 40-result cap, nonmodal opening, progressive append, label changes,
media limits, stale-response rejection, abort-on-close and keyboard-focus preview
loading without `IntersectionObserver`.
Run them with `node --test codex-runner/tests/test_run_sidebar_ui.cjs`.

This documentation pass inspected source and test definitions; it ran no browser,
backend, network, model or hardware action and makes no rendered-layout or actual
playback claim. Browser evidence for desktop/mobile layout, keyboard/focus
behavior, real scroll loading, playback/seeking, modal/fullscreen Escape behavior
and unavailable-media recovery belongs to the parent task's verification; this
source review does not establish those runtime results. No root `PRODUCT.md`,
`DESIGN.md` or `.impeccable/design.json` was available as a system authority, and
no design-system
file was created or modified for this ordinary extension. The nested RoboSkills
site is a separate surface. Accumulated stylesheet overrides and the pre-existing
mobile `runScores p` selector missing its class dot were not canonized or repaired.
