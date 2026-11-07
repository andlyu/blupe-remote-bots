# Hosted Works gallery

Hosted Works is a curated gallery of public BluPe research websites. The Robot
room header links to `/hosted_works/` beside API. Both `/hosted_works` and
`/hosted_works/` serve the gallery through `HostedRunner` in `playground.py`.
The former `/research` and `/research/` routes permanently redirect there.
Production mirrors these routes in `/etc/caddy/hosted-works.Caddyfile`; its static
handler and header asset can be updated without restarting the robot backend.

The page extends the existing dark, Arial, soft-blue interface. It does not
establish a new visual identity or replace the existing product/design documents.
The grid uses three columns, two at 1000px and below, and one at 600px and below.
Reduced-motion preferences disable the preview and hover animations.

The heading area introduces the gallery with “Find research on BluPe.” Both
research actions stay in this area: “Ask BluPe to host your method” opens an email
to BluPe's published contact, `info@blupe.io`, and “Harness to integrate your
method” opens the public shared integration-harness README. The hosting link
does not submit or send a message automatically.

## Content and provenance

ClawMetry appears first, followed by Spotter and Completion-Aware Guidance.
The owner removed RoboHarness, RoboSkills, EmbodiedEvo, MEMO and Agent as Policy
from this gallery on November 6, 2026; their services, sources and run histories
are unchanged. Their existing snapshot assets remain available at retained URLs.

The screenshots were captured from the public websites in Chrome on November 6,
2026. They are website snapshots, not live embeds or evidence of current robot
availability. Gallery presence is not physical task acceptance, a benchmark
result, or verification that an integration's physical requirements are complete.
Each website owns its current status and results.

| Website | Public URL | Screenshot |
| --- | --- | --- |
| ClawMetry | https://playground.clawmetry.com/ | `clawmetry.webp` |
| Spotter | https://spotter.54.209.185.15.sslip.io/ | `spotter.webp` |
| Completion-Aware Guidance | https://cag-molmoact-blupe.andlyu.chatgpt.site/ | `cag.webp` |

Gallery files live in `codex-runner/static/research/`: `index.html`, `gallery.css`,
`gallery.js`, the three listed WebP images plus retained historical snapshots,
and adjacent `.webp.json` provenance files. The JSON files record the capture source/date; they are not public assets.
`/static/research/` serves only the explicit `research_files` allowlist in
`playground.py`: the CSS, JavaScript and eight image filenames.

## Preview behavior

An ordinary click or keyboard activation opens a native modal `dialog` with the
snapshot, project description and Visit website link. The close button receives
initial focus. Escape uses the native dialog dismissal, and closing restores
focus to the originating gallery link. A backdrop click closes only when both
pointer-down and click occur outside the dialog bounds.

Modified clicks and middle clicks retain the direct external link. Without
JavaScript or native dialog support, the links still open the websites directly.
External links use a new tab with `noopener noreferrer`. The gallery does not
embed the workspaces, create robot sessions or submit robot runs.

## Maintenance

1. Edit the website title, description, URL, image path and useful image alt text
   together in `static/research/index.html`. Keep entries limited to intentionally
   public websites.
2. Capture the actual website in a browser and replace its WebP snapshot. The
   thumbnails use a top-aligned 1200:562 crop; the dialog shows the image at its
   natural aspect ratio. Update the adjacent provenance JSON and the visible
   capture-date label in the preview footer. If captures have different dates,
   give each preview its correct date rather than retaining a shared date.
3. When adding or renaming an image, update `research_files` in `playground.py`.
   Preserve its explicit allowlist. Check the route/asset coverage in
   `tests/test_hosted.py`, including the three-entry expectation when content
   changes. Verify preview open/close, Escape, focus return, direct modified-click
   navigation and the narrow-screen layout after UI changes.

The Robot room link is created in `static/meeting.js`; its compact navigation
styling is in `static/meeting.css`.

## Ownership

Shared gallery, runner routes and playground navigation belong in this
repository's `codex-runner/`. BluPe-only hosted billing, analytics, moderation and
deployment belong in `blupe-evals/apps/blupe_web`, which consumes the shared
repository; do not maintain an editable copied gallery there. See
[Repository ownership](../../docs/REPOSITORY-OWNERSHIP.md).
