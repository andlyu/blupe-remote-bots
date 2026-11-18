# Installed YAM1 linear4310 variant

The XML is the read-only installed i2rt1.1.2 capture already retained in
BluPe's robot-asset audit. SHA256:
`1ae64edff48e7a1d1de727d90c2a77a98aa519796b72233a26f2c1ab1bf66652`.
Its mount is identity and its grasp site is `(0,0,-.1347)` metres, matching
the canonical native YAM grasp frame. No new robot measurement was taken.

Do not describe this XML as identical to upstream commit
`120c3c81400171174604e503943f8d1ebc891058`. That exact upstream XML was
downloaded and hash-checked on2026-11-18: SHA256
`b30cf347d35b72dfc0e1c32d57f1c868e4d79a02d916d6dc5b48222a80544c64`.
It has a different gripper mount quaternion and grasp-site translation.
The scene adapter intentionally uses the captured installed variant.

The three original meshes are byte-identical to the installed capture and
these exact upstream files at that commit:

- [gripper.stl](https://raw.githubusercontent.com/i2rt-robotics/i2rt/120c3c81400171174604e503943f8d1ebc891058/i2rt/robot_models/gripper/linear_4310/assets/gripper.stl)
- [tip_left.stl](https://raw.githubusercontent.com/i2rt-robotics/i2rt/120c3c81400171174604e503943f8d1ebc891058/i2rt/robot_models/gripper/linear_4310/assets/tip_left.stl)
- [tip_right.stl](https://raw.githubusercontent.com/i2rt-robotics/i2rt/120c3c81400171174604e503943f8d1ebc891058/i2rt/robot_models/gripper/linear_4310/assets/tip_right.stl)

Their expected hashes are checked before scene compilation in yam1_scene.py.
MIT license from the same public I2RT revision is included as LICENSE.
Source: https://github.com/i2rt-robotics/i2rt/tree/120c3c81400171174604e503943f8d1ebc891058 .

The adapter adds nominal Google simulation finger gains/coupling and hides
visual IK markers. It does not establish measured contact forces, motor
calibration, independent camera accuracy or physical manipulation success.
