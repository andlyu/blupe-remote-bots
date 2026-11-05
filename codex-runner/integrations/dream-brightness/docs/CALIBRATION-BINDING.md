# Selected calibration in local Dream FK/IK

Andrew requested fixing the local Dream calibration gap and following the operator dashboard's selected saved profile. This is separate from the observed Dream HTTP response-header disconnection.

The runner reads the station's existing `GET /v1/robots/{robot_id}/calibration` report before queue admission. It validates robot/schema, original-encoder convention, the canonical model hash, both arms' finite corrections, model/camera IDs and base spacing. It rereads the selection after admission and before each new prediction. A changed binding aborts that run; it is not silently rebound. Other stations retain their existing native conventions.

Corrections are applied exactly once in generated per-arm URDF **geometry**, built from the hash-pinned canonical controller model. Original encoder feedback, outgoing joint values, physical zeroing and joint limits stay unchanged. Both selected arm corrections are retained, including J1/J6 when an operator zero-reference profile contains them. No calibration ID is hard-coded as the required selection.

The SDK's `joint_units` is a checkpoint-unit conversion, not an FK correction, and is not used to hide offsets. The native link-six frame is converted into Dream's trained TCP frame; the controlled point remains the canonical grasp point, with the native grasp orientation followed by +90 degrees about local Z. Base spacing also positions the SDK's existing camera-pole and inter-arm geometry. This does not disable gateway safety validation.

The isolated worker registers the generated arm descriptions before constructing SDK `ClientIK`, confirms the exact selected binding to its parent, and refuses a conflicting profile in an already prepared worker. A worker recovery must also reconfirm its geometry. SDK package files are not patched. Run configuration retains `kinematic_calibration`, `model_calibration_id` and camera `calibration_id`; brightness outcomes are grouped separately by calibration fingerprint.

## Verified software evidence

- Canonical controller model SHA256: `273d44b2829b433f8913abaf883419ca88170762bda3d50faa33fe886b73b42c`.
- Actual selected camera-fit model: `93c4db966dca49dbb831a2215f4dfc5fb83bf82eabfe99b3035a027aa7fc9275`; camera report: `40a9220259748447f0564404fbc0aa40e236786182992895cef9ee0e51f88f11`. These are observed evidence, not required constants.
- Native maintenance catalog independently reported the selected/controller/camera IDs synchronized and exposed both camera fit and right-arm zero trial. No profile was activated by this chat.
- Offline canonical-FK comparisons cover both arms, mixed joint signs, endpoint poses, unchanged limits and encoder values, dynamic profile changes, J1/J6 zero references and invalid/native bindings.
- Binding checks exercise run-config retention, worker confirmation, stale queued/mid-run profiles and recovery without silent stock geometry.
- The **actual Dream SDK1.0.0 ClientIK observation and trajectory solver** ran with synthetic poses and no network/model/robot request. Maximum measured numerical round-trip error: under0.24mm translation and0.15 degrees in encoder coordinates. This is a software consistency check, not physical accuracy.
- The installed SDK URDF remained unchanged at SHA256 `90e1bb509b7be077c42c660e4528d5b8dad6fceca6e3780bd051c5f14b09c548`.

Receipts are retained in the task's `outputs/dream-brightness-01a1a8a1/`: `calibration-core-preflight-final.xml` (202 tests +6 subtests), `calibration-experiment-preflight.xml` (48 tests through the actual deployed trajectory parser), `calibration-binding.xml`, `sdk-calibration-proof.json`, and `sdk-calibration-probe-input.json`. The first probe attempts exposed incomplete offline camera-role/argument fixtures; those fixtures were corrected before the passing actual-SDK run. They were not physical trials.

The reproducible numerical probe is `codex-runner/tests/dream_calibration_sdk_probe.py`, run in the installed Dream SDK environment with `--runner-name` supplied explicitly. It asserts SDK FK against controller reference targets and encoder/EEF trajectory round trips, waits for actual trajectory compilation, and asserts unchanged package geometry.

## Limits and current acceptance

This software fix does not establish better physical manipulation accuracy, fix the independent inference-service disconnection, or make the earlier unmatched brightness trials controlled. Earlier runs lacked this binding and remain historical. New physical acceptance, matched initial scenes, startup timing and final deployment verification remain unchecked in the integration checklist.

`GET /experiment/calibration` checks the live selection through the loaded runner and returns its source revision. It does not start a worker, inference or robot run. The website distinguishes a checked selected profile from the actual profile retained in an executed run.

The first live inspection returned503 because `CameraFrameSource.allowed_origin` is a validated `(scheme, host, port)` tuple, while the calibration API client accepts a URL. The adapter now reconstructs that origin, including explicit ports and bracketed IPv6. Three regression cases reproduced the failure before the fix; all22 binding tests then passed in0.40s. Receipt: `evidence/calibration/calibration-camera-origin-regression.xml`. This live inspection did not start a model or hardware run.

Actual process protocol verification also found that `dream_worker` puts configuration results inside `reply.result`. The adapter now checks the nested binding both during initial preparation and recovery. Fixtures use that actual envelope and reject a misleading top-level binding. Two real SDK worker processes were fully primed, then passed through the actual DreamAdapter preparation handshake:34.158s and21.185s. No observations, predictions, queue entries or physical commands occurred. `evidence/calibration/public-sdk-preparation.json` records actual source-module hashes and readiness. The reusable `codex-runner/tests/dream_calibration_worker_probe.py` requires explicit SDK/credential/state/output paths and confirmed runner name.
