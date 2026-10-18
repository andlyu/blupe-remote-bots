# Optional camera super-resolution

Expanding a synchronized camera reveals an **Enhance** toggle. The viewer uses
the visitor's WebGPU device in a worker. Switching it off immediately shows the
original video. The choice is remembered in this browser. The four-view grid,
recordings, sensor capture, model inputs, and robot controls are unchanged.

The live model is FSRCNN ×2, using weights from
[Saafke/FSRCNN_Tensorflow](https://github.com/Saafke/FSRCNN_Tensorflow).
The frozen graph is converted to dynamic ONNX with the original convolution
weights and PReLU slopes; the independent NHWC reference differs by less than
7e-7 on the conversion fixture. The FP16 version is selected only when the GPU
supports shader-f16. Input/output tensors remain float32. Source chroma is
retained and the network enhances luminance.

Input is capped at 960×540 pixels with preserved aspect ratio. Thus the detail
views process their native 640×360, while a 1920×1080 observer uses a 960×540
working image and returns a sharpened 1920×1080 image. This is display
enhancement, not new sensor detail. The default is enabled only while expanded.

There is one in-flight frame and no pending-frame queue. Results older than
200ms are discarded. Three slow results (over 125ms processing) return to the
original video; stalled jobs terminate after two seconds. Closing the view,
switching cameras or hiding the page terminates the worker. Unsupported GPU,
runtime/model loading failures and device loss retain the original video.
The displayed `+N ms` measures the additional snapshot-to-enhanced-display age.

## Model and runtime selection

The Real-ESRGAN general-x4v3 still-image preview is too slow for live playback on
the tested M1 Pro browser: 601–907ms per 640×360 frame. FSRCNN preserves more
source texture and runs with substantially lower cost. A local real-image
worker check measured about 65ms for a detail view and 107ms for the observer
working size, including conversion and drawing. These spot measurements are
not a guarantee on other devices or under load. The preview and live models
are different; do not describe the preview as the live implementation.

ONNX Runtime Web 1.23.2 is served from the same origin, with its MIT license.
FSRCNN's Apache 2.0 license is included. The 24MB WASM runtime loads only when
enhancement starts. No third-party inference service or image upload is used.

Local serving whitelists the assets under `/static/super-resolution/`. The CSP
permits same-origin workers and `wasm-unsafe-eval` for WASM compilation; it
does not permit general JavaScript eval. Hosted Caddy deployments must preserve
these directives and may serve the asset directory directly without a runner
restart. Preserve unrelated live HTML/Caddy changes during rollout.
