# Released full XYZ planning: physical results

Current acceptance remains12/15;7,13,15 are open. No successful stack or complete
grasp/lift/transfer/release/withdrawal qualification is claimed.

PR201/source73d944d merged5887975 after all6 required checks passed. Immutable
runtime provider78857/physical78860 is healthy; simulation14674 was preserved.
Actual run configuration and model request events verify Sol/none startup,
Astra/medium afterward and the initialf9/subsequent634 template hashes. The
pinned upstream agent SHA7635fe4... is unchanged. An exact production-callback
[availability probe](2026-10-31-production-callback-offline.json) using its
sanitized environment also returned an Astra
program in26.090s; that offline program was not executed.

Run[c77e42b3](2026-10-31-xyz-run-timing.json) used the normal Site19 form,
confirmed runner and fresh source31083/target314108 marks. Its first right
approach passed at1.566mm/.251deg after one bounded correction. Right object-mask
depth was insufficient; the left mask had1071of1071 valid pixels. The agent then
stopped before contact because nearby-box/open-finger clearance was unresolved
under the experimental calibration. Total57waypoints/2packets,89.778s native
window, no grasp/stack. The matching59s replay actually played and sought40s,
with camera07:33:50.5PDT and honest task-not-completed/unscored assessment.
Nativepark/torqueoff/autoqueue verified.

Original camera proof shows unchanged07:33:03.9 then clearly moved07:33:05.9,
with0.1s precision allowance. PostHome upper13.797700s and fullRun28.520265s
both pass without queue deduction. The observed11.105074s join/admit interval
is retained separately, not claimed as a native database timestamp. See
[timed UI](2026-10-31-xyz-timed-ui.mp4), [original manifest](2026-10-31-xyz-ui-frames.json),
[before](2026-10-31-xyz-before-motion.png), [moved](2026-10-31-xyz-motion.png)
and [replay proof](2026-10-31-xyz-replay.png).

Run[c7468c5d](2026-10-31-inspection-run-timing.json) used the same released source
and a normal task-field clarification allowing a demonstrably clear noncontact
retreat/reobserve before giving up. The left approach completed, then a40mm
nominal retreat reached81.34mmZ versus85.49mm requested. The existing exact move
failed at5.227mm position residual after bounded correction; the subsequent
observe() was never reached. Total79waypoints/10packets,68.613s native window,
no grasp/stack. Its matching46s replay played and sought34s, camera07:43:40.6PDT,
with the exact measured failure and no-native-score label. Nativepark/torqueoff
verified; no failed/uncertain movement was replayed.

The10.6s initial model call was slower than c77's6.3s; both generated the same
short initial structure. Causation is not established. Camera first motion
upper18.291528s fails15s after Home; packet preparation alone was at least
16.739395s after Home, confirming the miss independently. RawRun upper30.731225s,
with the observed10.200185s initial queue interval subtracted once, yields
20.531041s and passes30s. This new postHome miss is outside the accepted exact
historical exceptions. See [timed UI](2026-10-31-inspection-timed-ui.mp4),
[manifest](2026-10-31-inspection-ui-frames.json),
[before](2026-10-31-inspection-before-motion.png),
[moved](2026-10-31-inspection-motion.png) and
[replay proof](2026-10-31-inspection-replay.png).

Timed clips preserve actual post-submission screenshot cadence; earlier
preflight images remain in the original manifests. Omitted identity-entry
intervals are not represented as continuous capture. Replay playback time is
not wall-clock evidence. Email/capabilities and the specifically excluded old
recording are absent from these artifacts.

The precision contract behaved as declared. Further work must distinguish a
useful camera-view region, using fresh measured-pose RGB-D, from precise grasp
motion. A dedicated inspection command and compact first inspection call are
proposed; none is implemented or qualified by this evidence. Contact/controller
cause of earlier tracking errors remains unproven. Existing native bounds,
queue/lease/readiness/Stop, precise-move checks and non-replay remain intact.
