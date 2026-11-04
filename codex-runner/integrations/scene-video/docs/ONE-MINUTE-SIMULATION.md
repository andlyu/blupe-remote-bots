# One-minute scene capture motion

The user accepted this simulation and requested integration with the playground
and an actual recording. `MinutePolicy` now generates the same route from fresh
leased Home feedback through the normal runner. The physical run completed all
600 points; see [physical evidence](evidence/minute-physical.json) and
[publication](evidence/minute-publication.json). The live entry point is
`minute.py serve`, with a 120-second maximum session allowance.

| Planned seconds | Motion |
| --- | --- |
| 0–6 | Raise both cameras and aim at the shared center |
| 6–14 | Right camera moves forward |
| 14–20 | Right camera moves sideways and scans across the scene |
| 20–28 | Right camera returns to a wider view |
| 28–36 | Left camera moves forward |
| 36–42 | Left camera moves sideways and scans across the scene |
| 42–50 | Left camera returns to a wider view |
| 50–60 | Both cameras advance, aiming at different near/far scene regions |

The grasp reaches X=0.47 m, below the existing 0.48 m bound; Home is about 0.30 m.
Camera positions span about 21 cm forward, 16 cm sideways and 11 cm vertically.
Each camera travels roughly 80 cm along its entire smooth path. Camera roll may
change to keep the aimed motion inside the existing wrist limits. An earlier
fixed-upright inward scan failed IK and was rejected without dispatch.

The real serializer accepts two 300-point packets. The offline controller
snapshot approves 1,076 swept collision samples; maximum adjacent joint change
is 0.02859 rad per 100 ms, below the existing 0.035 rad planning cap. Both physical
packets also passed the actual gateway and completed with settled feedback.
Grippers preserve the original measured fractions. Fresh feedback, identity,
pacing and hardware checks remain enforced at the second packet's join.

The [labelled simulation](evidence/minute-simulation.mp4) is exactly 60 seconds,
with left wrist, overview and right wrist panes. All 600 frames decode and seek.
It uses retained YAM-1 camera calibration and a synthetic table with objects
spread across it. Synthetic-grid projection enters each camera's frame at some
point, compared with about 75%/62% for the original fixed-angle sweep. Projection
ignores occlusion and does not certify actual scene coverage or reconstruction.
The render is kinematic and does not predict controller execution time.

Actual hardware execution took 73.81 seconds including settling, and the saved
full-speed movie is 84.6 seconds including setup and packet gaps. No content was
sped up or removed from the full movie. The separate four-camera viewing preview
is 10× and removes idle periods. Two missing-image ticks remain labelled in the
full movie; the recorder reported zero capture errors and one missed tick.

The first physical progress was reported 4.66 seconds after matched Home
completion. Live UI screenshots showed moved arms by 11.63 seconds after Home,
24.31 seconds after Run. A continuous timed UI screen recording was not retained,
so the broader harness timing-certification box remains unchecked.
