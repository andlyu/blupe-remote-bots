# Dream Labs SDK 1.0.0 reference

Authoritative READMEs extracted from the installed 1.0.0 wheel metadata on October 19, 2026. License: Apache-2.0. Upstream GitHub page could not be fetched; these references match the tested SDK, rather than an unpinned main branch.

| Use case | Reference |
| --- | --- |
| Isolated Python 3.12 installation and optional station dependencies | [Library](library.md#install) |
| Private credential file, model discovery and nonmotion setup | [Client](client.md#quickstart) |
| Three camera roles, JPEG encoding, monotonic history and radians | [Client](client.md#running-a-model) |
| Mid-run language guidance: latest observation replaces `prompt`; `get_action` consumes it without an episode reset | [Client](client.md#running-a-model), [runner integration](../../runtime-steering.md#dream-1-prediction-boundary) |
| EEF trajectory IK, completion anchor and joint chunk output | [Client](client.md#eef-checkpoints-and-client-ik) |
| Session reset, release and recording disable | [Client](client.md#running-a-model) |

Our bridge follows the documented YAM embodiment block and EEF `solve: traj` contract. It never imports or launches the SDK robot station/motor driver. The source package's `dream_examples/yam_mujoco/dream_control.py` and `robots/yam.py` were also read locally to confirm arm order and gripper/radian conventions; they are not copied as application code.

## Blockwise linear algebra

Pinned private API/source contract, activation and numerical limits:
[BLOCKWISE-GRAM.md](BLOCKWISE-GRAM.md).

Dedicated SDK subprocess BLAS defaults, explicit overrides and the measured
YAM1 thread-contention regression: [CPU-THREADS.md](CPU-THREADS.md).
