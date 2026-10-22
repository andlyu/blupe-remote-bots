# Observer enhancement preview

Open the playground with `?observer_enhance=1` (append with `&` when other query parameters exist). This opt-in viewing experiment adds a before/after divider and strength slider for the observer canvas. Both sides use the same decoded frame. It requests no additional video stream and does not change camera capture, encoder resolution, robot commands, or model input images.

Auto uses a noise-aware WebGL2 RCAS sharpening pass when available; otherwise it uses the same algorithm in a CPU Web Worker. Select CPU to force software processing, or add `&enhancement_engine=cpu` to the preview link. CPU work has one frame in flight; busy workers skip intermediate incoming frames rather than build a queue. The before/after pair stays matched. The enhancement preview can run slower than the underlying stream on a slow device.

Render size follows the displayed image, capped at native dimensions and device pixel ratio2. Hidden pages stop submitting work. On/off and processing controls remain usable in the phone camera dialog. These are spatial sharpening filters, not neural or multiframe super-resolution; enlarging or sharpening cannot guarantee recovery of missing source detail.

Deploy `observer-enhancement-worker.js` alongside the shared static assets. Static reverse proxies that enumerate paths must allow `/static/observer-enhancement-worker.js`. The existing same-origin script/worker policy is sufficient; no inline-style or blob-worker exception is needed. CSS is served in hosted.css.

Shader/CPU port attribution and MIT license are included in the sources. Algorithm: AMD FidelityFX FSR1 RCAS, https://github.com/GPUOpen-Effects/FidelityFX-FSR.

Validation: `node --test codex-runner/tests/test_observer_enhancement_cpu.cjs codex-runner/tests/test_camera_expansion.cjs`. Browser pixel fixtures additionally check orientation, unchanged original/zero-strength pixels, flat-region stability, split identity and CPU/GPU agreement. Mobile viewport checks do not establish physical-phone battery or temperature behavior.
