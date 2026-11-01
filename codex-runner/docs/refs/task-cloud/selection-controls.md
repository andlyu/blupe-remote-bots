# Selection control references —31October2026

The user requested established3D-selection examples and copying their behavior.
These primary examples were read and visually inspected before implementation.

| Reference | Observed pattern | Adopted behavior |
| --- | --- | --- |
| [Three.js transform demo](https://threejs.org/examples/misc_controls_transform.html) | Distinct translate/rotate/scale modes; colored axes; arrow/cube/ring handles; W/E/R shortcuts | Move/Resize/Rotate tools, matching axis colors and handle shapes, same scoped shortcuts |
| [Potree clipping demo](https://potree.org/potree/examples/clipping_volume.html) and [example source](https://github.com/potree/potree/blob/develop/examples/clipping_volume.html) | A finite box within the point cloud, with inside/outside/highlight choices | Keep selected runs distinct and dim the rest while preserving the surrounding cloud |
| [CloudCompare Cross Section](https://www.cloudcompare.org/doc/wiki/index.php/Cross_Section) | Face interactors alter boundaries; rings rotate; box position/dimensions and predefined views are separately editable | One-face resizing with the opposite face fixed, axis movement, ring rotation, numeric/range alternatives and camera presets |

The existing Canvas renderer and3D membership remain in use. This is an adaptation
of interaction patterns; no Three.js/Potree/CloudCompare source or runtime library
was imported. Existing labels, filter scope and replay permissions are retained.
Our descriptive run count, binary success rate, unknown coverage and observed
median prompt are additions specific to BluPe.

Browser evidence includes the official Three.js translate/resize/rotate modes,
the loaded Potree clipping scene, and our desktop/phone controls. Geometry and
native-interaction evidence are retained in the task verification checklist.
