# Tested deployed canonical validator

This is the unmodified trajectory parser captured from the Robo-house YAM controller before the November4,2026 physical pilot. SHA256: `1c640b6d144d8b55c2a77ae584e71a91cb50d036ddc5d548fe4d656dd5d74483`. The adjacent controller checkout had a different parser; the gate used these exact deployed bytes.

The source is the shared controller implementation of `src/blupe_controller/runtime/YAM_control/joint_trajectory.py` in [blupe-playground-robot-controller](https://github.com/andlyu/blupe-playground-robot-controller). No validator logic is changed here. This retained snapshot makes the historical command-contract test reproducible; it does not establish that a future deployment has the same bytes. Before another physical release, capture/verify the actual deployed parser and rerun the gate with `YAM_CANONICAL_TRAJECTORY` pointing to it.
