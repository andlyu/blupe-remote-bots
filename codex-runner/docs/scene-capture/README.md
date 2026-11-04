# Guided scene capture

Public route: https://d39laae2ep8en8.cloudfront.net/scene-capture.html

This extends the existing deployed Path Studio, preserving its origin/CSRF controls, per-visitor identity and controller, queue/lease/readiness, command validation and Stop. The drawing studio remains accessible.

1. Set forward reach (380–470 mm), inward scan width (50–150 mm), forward scene aim (500–600 mm), and planned duration (60/90/120 s). YAM1 and both arms are fixed for this method. Grippers hold measured starting fractions.
2. Simulate the exact configuration. The server reads calibration only, plans the complete path, checks installed CAD sweeps, packet pacing and wrist-camera tabletop aim, then returns joint frames and calibrated camera poses. Review 3D/left/right views; roll is preserved. Scene objects are illustrative. Camera projection is a pinhole approximation at native image aspect ratio.
3. Enter actual identity and press Run. The server requires a visitor-scoped, single-use simulation receipt bound to configuration, calibration and planner sources, expiring after30min. Real execution replans from fresh safe measured Home. Any changed config, build or calibration requires simulation again. No uncertain movement is replayed. Stop remains available while acknowledgement is uncertain.
4. Recording finalizes on existing direct USB storage. The task-scoped saved-data worker yields to active leases, camera health or storage/memory constraints; sends only this method's finalized recordings to the existing canonical HF publisher. Export/transfer retries never move the robot. The website resolves the exact source ID to its complete immutable LeRobot episode (left/top/right videos + joint state/action Parquet), then exposes its viewer and native files. Camera exposure timestamps and invalid-row flags remain present; these cameras are not hardware synchronized.

The previous capture is episode602, source ep_47151c9fe197419d, published at b2fe3e4110013f127e0baee887965c4e4419cc0c. It is explicitly labeled as a previous recording in the UI.

## Verification

42 Python tests and13 JS tests passed; Python command44.88s. New capture tests execute the actual IK/CAD/serializer, all three durations and gate failures, measured gripper fractions and uncertain packet rejection. Browser checks at1280px and390px: working simulation, camera roll/aspect visible, no horizontal overflow, config-change review reset/Run disable, clean console. Default simulation600points/1077CADsamples/max joint step0.028588708rad; local computation0.27s excluding API readiness. Impeccable finish review: ship, no material fixes. No claim that queue/Home time is below15s: planned duration, wall-clock motion and complete recording are separate.

Deployment and end-to-end automatic publication evidence are pending until recorded below. The full inherited harness checklist is retained separately; open broad requirements are not waived.
