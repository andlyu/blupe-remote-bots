# YAM1 adapted Robotics controller

Write `controller.py` with `def run(env):`. The worker supplies this same API
for isolated MuJoCo and the host-validated physical bridge. Use Google's
published Robotics skills for reasoning, perception and planning, adapting
their stock single-arm calls to these two named arms. Do not open CAN/devices
or construct another robot owner. The execution container has no network/key.

- `env.left.q_arm`, `env.right.q_arm`: measured six-joint float64 radians.
- `env.left.gripper`, `env.right.gripper`: measured normalized opening0..1.
- `env.left.move_joint(q, gripper=None, duration_s=1.)` (also right): six native
  radian targets and optional opening; exact validated10Hz canonical packets.
- `env.left.set_gripper(value, duration_s=.5)` (also right): gripper-only packet
  preserving every measured uninstructed joint/other-arm/gripper field.
- `env.left.fk_world_ee()` (also right): current4x4 native grasp pose in the
  common world frame (x forward, y left, z up; left base y=+.25m, right=-.25m
  for the packaged0.50m spacing). This is distinct from the native guard's
  separate workspace frame; do not replace its checks.
- `env.left.solve_arm_ik([x,y,z], target_rot_world=None)` (also right): Google's
  published generic site IK on the installed model, with strict finite inputs,
  native limits and independently checked achieved residuals. Result is six
  radians; call move_joint to request execution. IK alone sends no command.
- `env.measurements['top'|'left'|'right']`: measured RGB8 arrays.
- `env.camera_opencv('top'|'left'|'right')`: RGB, K, T_world_cam, source capture
  timestamp and calibration ID. Intrinsics are pinhole; source camera extrinsics
  remain provisional and real Brown distortion is not reproduced in simulation.
- `env.observe()`: refresh measured state/images without sending an actuator
  packet. `env.close()` ends the controller; the outer runner owns parking.

Joint commands use the unchanged calibrated native bounds and speed/packet
budgets; inspect commands_spec on env.device_layer. Gripper targets are strict
finite0..1, not percentages/degrees. Invalid raw values are rejected, including
tiny out-of-range floats. Do not clamp an invalid target. Catch a local
LocalCommandRejected only to make a new plan using the refreshed measured state.
Do not replay a timeout, unknown execution outcome or physical safety failure.

The current snapshot includes live images and matching installed robot geometry.
Object geometry/contact reconstruction is still pending. Do not claim an object
task passed just because code completed. Use visible images and feedback, never
privileged object poses. Robot inertias/gains remain nominal; contact force has
not been independently calibrated. Simulation results always retain these limits.
The isolated rollout records top-camera video at10Hz and caps actual simulation
time (including joint settling) at60seconds. Endpoints preserve exact requested
values; observation is actual integrated/physical feedback, not a target echo.
