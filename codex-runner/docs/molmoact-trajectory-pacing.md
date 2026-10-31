# MolmoAct2 gateway pacing

The main Playground MolmoAct2 adapter selects every third target from the
30 Hz model output for the 10 Hz gateway. A selected transition can exceed the
station step or velocity limit, even when model inference is valid.

The adapter preserves every selected absolute joint/gripper target and inserts
linear intermediate samples when any arm joint changes by more than 0.03 rad.
At 10 Hz the planned peak joint speed is at most 0.3 rad/s. Larger movements
therefore take longer than the original one-second prediction horizon. Model
weights, raw predictions and camera preprocessing are unchanged.

The entry segment uses feedback refreshed after inference through the existing
controller lease/identity/readiness checks. Packet and session waypoint budgets
still reject the whole expanded chunk if it cannot fit. Stop, position,
workspace, collision and native hardware checks remain authoritative. Hardware
rejections and timeouts are not automatically retried. Other adapters retain
their existing behavior. Public run configuration and the interaction journal
record the pacing bound and expanded waypoint count.

## Recorded reproduction

On October 30, 2026, `run_29e1fe33eb8e4af3879b661fc90b0b42` /
`ep_bdb75297bfe94c86` completed 40 waypoints before packet `_40` was rejected
with `adjacent_delta_limit`, zero packet progress. Its largest internal jump was
right joint 3, 76.54358 to 93.55326 degrees: 0.296875 rad in 100 ms.

Replaying the recorded ten selected targets through pacing produces 50
waypoints, with peak step 0.0296875 rad and peak speed 0.296875 rad/s. The local
native guard speed/step/position check accepts this expanded packet. That
analysis used mocked FK and clear-collision functions; it does not establish
physical clearance or task success. The live station configuration is separate
from the repository default used in the offline guard check.

Regression tests cover this jump size on both arms, at chunk entry and inside
the packet, exact endpoint preservation, unchanged raw predictions/grippers,
small-chunk duration, expanded budgets, fresh leased feedback, Stop and lease
failure. Final deployment and physical-run verification are recorded separately.
