---
name: Path Studio scene capture
description: Surface-specific design and interaction contracts for guided camera capture.
---

# Design System: Path Studio scene capture

## Overview

This is a narrow extension of the incumbent Path Studio interface. Its forest surfaces, lime actions and Manrope type remain the visual authority. This document records the added capture surface; it does not replace the repository root design system or introduce a new brand.

The four linked workflow steps retain their current status in the page: Set path, Simulate, Record and HF episode. A compact settings column supports a larger simulation viewer; identity, recording and episode delivery follow below. The [feature README](README.md) describes the method and backend contracts.

## Colors

The deep forest page background (`#101a14`) and pale text (`#ecf1e6`) continue Path Studio. Lime (`#c6f432`) marks primary actions, selected simulation views, workflow numerals and keyboard focus. Secondary controls use a muted forest fill (`#253125`) and quiet outlines. Stop uses a rust surface with a warm label; errors use warm pale text. Simulation object colors and CAD materials describe illustrative scene content, not UI palette tokens.

## Typography

Manrope is served locally with a sans-serif fallback. Body copy uses (14px) with a generous (1.65) line height; the introductory description uses (16px). The main heading scales from (32px) to (46px), while section headings use (20px). Labels and operational details use (12–13px). Range values and simulation time use tabular numerals so updates do not shift their columns.

## Layout

The desktop content is capped at (1480px) and padded by (4vw). Settings occupy a (290px) column beside a flexible viewer, with a (38px) gap. At widths of (900px) and below, the settings column becomes (240px) and the gap (24px). Recording and episode output share two columns below a section divider while idle. During an active or uncertain run, Record expands across the handoff width, episode output moves below it, and the identity, review and Run controls are hidden. The Record heading and Stop remain sticky at the top of the viewport.

At widths of (660px) and below, the workflow becomes a two-by-two grid and the workbench stacks in reading order: settings, simulation, recording, episode output. Page padding becomes (5vw). The identity fields remain paired on phones; both sections fit the viewport without requiring horizontal scrolling. Simulation view controls wrap when needed. Within Record, the overhead camera spans the full width above the paired left and right wrist views; desktop shows the three cameras side by side.

The simulation viewport is (360px) high on desktop, (430px) at widths of at least (1500px), and (310px) at narrower breakpoints. The user can select Three views, 3D motion, Left wrist or Right wrist. Initial narrow-screen rendering selects 3D motion; selecting a wrist view gives that camera the full viewer area. Wrist images retain their recorded (16:9) aspect ratio within the available area. Camera roll remains visible.

## Elevation & Depth

Tonal separation and thin borders establish grouping. There are no decorative card shadows. The viewer is a single framed area; section dividers separate setup, recording and delivery without boxing every text group. Reduced-motion preference removes smooth page scrolling. Simulation playback begins only through the user's playback control.

## Shapes

Controls have modest corners: buttons (7px), text fields and selects (6px), and the viewer (10px). Most controls have a minimum height of (44px); compact simulation-view buttons use (36px). These values describe this surface's existing implementation rather than a new repository-wide scale.

## Components

- **Workflow navigation:** four numbered anchor links, each with a persistent status line. Their statuses distinguish required simulation, passed review, queued/running activity and episode publication.
- **Guided preset:** reach, inward scan width, scene aim and planned duration remain visibly editable before a run. Their values are labeled with units. Changing any setting invalidates the previous simulation receipt and review, disables Run, and labels the preview as out of date.
- **Simulation viewer:** explicitly labeled illustrative, with no robot session. Playback and scrubbing expose the same path's arm motion and calibrated camera poses. A verification line reports the checked path, and the disclosure states simulation limits. A failed WebGL preview leaves Run gated.
- **Review and identity:** editable real-name and queue-email fields precede the review checkbox. Run requires a current successful simulation, checked review, valid identity, connection and an idle session. Prefilled identity remains editable. Explanatory copy distinguishes public runs from queue email privacy.
- **Robot cameras:** the Record panel always refreshes left wrist, overhead and right wrist previews before, during and after a run. Each camera polls independently, waits for its pending request to finish, and schedules the next request after (1 second). A (7-second) timeout or image error shows an unavailable placeholder and retries without overlapping pending requests. Per-camera update timestamps remain visually quiet and outside live regions; an aggregate polite status announces only failure and recovery transitions.
- **Run and Stop:** pending, queue, recording and completion messages remain inline. Settings lock during submission and activity. An uncertain submission stays locked until status resolves it. Stop stays available in the sticky Record header while acknowledgement is uncertain, and reconnecting observes the existing run without replaying motion.
- **Episode delivery:** publication progress follows the exact new source episode. Once ready, the prominent HF viewer link is accompanied by left, overhead and right videos, joint state/actions, row counts and quality counts. Publication lookup has its own retry control; it does not submit motion. The earlier verified episode remains explicitly labeled as a previous recording.
- **Accessible state:** operational messages use polite live regions, view buttons expose pressed state, native inputs retain labels, and keyboard focus uses a visible lime outline. Disabled controls retain their labels and use reduced opacity.

Ground truth: [HTML](../../static/scene-capture.html), [styles](../../static/scene-capture.css), [interaction state](../../static/scene-capture.js) and [simulation view](../../static/scene-capture-view.js). Desktop and phone review captures were checked at `/private/tmp/scene-capture-ui/desktop.jpg` and `/private/tmp/scene-capture-ui/mobile.jpg`. The live-camera layout was checked at `/private/tmp/scene-live-cameras-ui/running-desktop.jpg` and `/private/tmp/scene-live-cameras-ui/running-mobile.jpg` with real camera JPEGs in a labeled read-only running-layout fixture while the robot was parked; these captures do not evidence a physical run or new identity data.

## Do's and Don'ts

- **Do** preserve the incumbent Path Studio palette, locally served type and direct control labels.
- **Do** keep planned trajectory duration separate from queue/Home/settling time and full recording duration.
- **Do** retain visible simulation limitations, camera tilt and publication progress.
- **Don't** label an illustrative simulation or previous episode as the new physical capture.
- **Don't** enable motion from a stale configuration or retry uncertain motion automatically.

Not canonized or repaired: the unrelated root meeting-experiment design record and its pre-existing stale-sidecar hint remain outside this feature's scope. No root design or sidecar was regenerated.
