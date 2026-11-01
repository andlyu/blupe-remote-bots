# Task cloud rendering and touch previews

The canvas draws at the screen pixel ratio, capped at 3×. Smaller markers with a
light edge separate overlapping attempts; softer area tints keep point colors
legible. Coordinates, semantic projection, label calculation and selections are
unchanged.

On touch screens, a fixed pointer appears above the canvas center so the bottom
preview does not cover it. Drag/orbit or pinch the cloud, then release: the nearest
point within 20 CSS pixels is previewed after 180 ms. The acquired point is
emphasized. Dragging, drawing a selection and editing its handles suppress
previews. A direct tap on a dot also previews it without opening replay. The
preview remains visible after the finger lifts; its native **Open run** button
opens the matching run in the existing replay sidebar.

Mouse hover/click and keyboard focus, `[`, `]`, Enter and Escape retain their
existing behavior. Pointer cancellation, reset, resize, filters, robot changes,
and explicit preview cleanup cancel pending touch acquisition. Moving keyboard
focus from the canvas to the preview action preserves the action. Touch preview
media shares the existing bounded cache and respects reduced motion, playback
failure and unavailable-video states.

Verification: `node --test codex-runner/tests/*.cjs` includes regressions for
settled acquisition, no loading during gestures, cancellation, tap versus click,
focus transfer, exact replay callback, switching input methods and 3× rendering.
Browser checks use Chromium with synthesized touch and real public recordings;
physical iOS/Android testing is not claimed.
