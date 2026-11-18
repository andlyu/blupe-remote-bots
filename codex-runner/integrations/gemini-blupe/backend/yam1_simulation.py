"""MuJoCo DeviceLayer for the adapted bimanual YAM1 controller interface.

Uses the same native packet compiler as the host RPC bridge. Simulation state
is integrated, never overwritten with a desired target after execution. The
scene's collision/dynamics limitations remain explicit in its receipt.
Google reference: mujoco_playground c9de052f robots/yam/sim/device.py.
"""
import math
import time

from dm_env import specs
import mujoco
import numpy as np

from yam_commands import YamCommands, CommandRejected, CADENCE_HZ
from yam1_environment import LocalCommandRejected
from yam1_scene import ARMS, FINGER_TRAVEL_M


class SimulatedDeviceLayer:
    def __init__(self, scene, runner_root, *, render_cameras=True, on_step=None):
        self.scene = scene
        self.model = scene.model
        self.data = mujoco.MjData(self.model)
        self.data.qpos[:] = scene.data.qpos
        self.data.ctrl[:] = scene.data.ctrl
        mujoco.mj_forward(self.model, self.data)
        self.compiler = YamCommands(runner_root)
        self.render_cameras, self.on_step = render_cameras, on_step
        self.renderer = None
        self.cursor = 0
        self.closed = False
        self.packets = []
        self.steps_per_command = int(round(1 / CADENCE_HZ / self.model.opt.timestep))
        if not math.isclose(self.steps_per_command * self.model.opt.timestep, 1/CADENCE_HZ, abs_tol=1e-12):
            raise ValueError('Simulation timestep must divide the native command period')

    def measurements_spec(self):
        result = {f'{arm}/follower/joint_position/{joint}':specs.Array((), np.float64)
                  for arm in ARMS for joint in [*[f'joint{i}' for i in range(1,7)], 'gripper']}
        if self.render_cameras:
            for name, camera in self.scene.calibration['cameras'].items():
                width, height = camera['image_size']
                result[name] = specs.Array((height, width, 3), np.uint8)
        return result

    def commands_spec(self):
        result = {}
        for i, arm in enumerate(ARMS):
            for j in range(7):
                name = f'joint{j+1}' if j < 6 else 'gripper'
                low = self.compiler.safety['joint_lower_rad'][i*6+j] if j < 6 else 0.
                high = self.compiler.safety['joint_upper_rad'][i*6+j] if j < 6 else 1.
                result[f'{arm}/follower/goal_position/{name}'] = specs.BoundedArray((), np.float64, low, high)
        return result

    def observation(self):
        result = dict(source='simulation', observed_at=time.time(), sim_time_s=float(self.data.time))
        for arm in ARMS:
            q = self.data.qpos[self.scene.arm_qpos[arm]]
            result[arm + '_joints_deg'] = np.rad2deg(q).tolist()
            finger = float(self.data.qpos[self.scene.finger_qpos[arm][0]])
            # Published Google device measurement normalization; this does not
            # clamp requested commands, which the shared compiler validates.
            result[arm + '_gripper'] = float(np.clip(finger / FINGER_TRAVEL_M, 0., 1.))
        return result

    def render(self, camera, *, width=None, height=None):
        if camera not in self.scene.calibration['cameras']:
            raise ValueError('Choose top, left or right camera')
        native_width, native_height = self.scene.calibration['cameras'][camera]['image_size']
        width, height = width or native_width, height or native_height
        if self.renderer is None or (self.renderer.width, self.renderer.height) != (width, height):
            if self.renderer is not None: self.renderer.close()
            self.renderer = mujoco.Renderer(self.model, width=width, height=height)
        self.renderer.update_scene(self.data, camera=camera)
        return self.renderer.render().copy()

    def _measurements(self):
        observation = self.observation()
        result = dict(source='simulation', observed_at=observation['observed_at'],
                      sim_time_s=observation['sim_time_s'])
        for arm in ARMS:
            for j, value in enumerate(self.data.qpos[self.scene.arm_qpos[arm]], 1):
                result[f'{arm}/follower/joint_position/joint{j}'] = np.float64(value)
            result[f'{arm}/follower/joint_position/gripper'] = np.float64(observation[arm + '_gripper'])
        if self.render_cameras:
            for name in self.scene.calibration['cameras']:
                result[name] = self.render(name)
                result[name + '/captured_at'] = observation['observed_at']
        return result

    def begin_stepping(self):
        if self.closed: raise RuntimeError('Simulated DeviceLayer has ended')
        return self._measurements()

    def apply(self, commands, duration_s):
        if self.closed: raise RuntimeError('Simulated DeviceLayer has ended')
        try:
            points = self.compiler.compile(dict(commands=commands, duration_s=duration_s), self.observation(), self.cursor)
        except CommandRejected as exc:
            raise LocalCommandRejected(str(exc)) from exc
        # The complete packet is validated before any simulated actuator step.
        # Preserve it independently of physics state for exact endpoint review.
        self.packets.append(dict(first_step=self.cursor, waypoints=points))
        for point in points:
            for arm in ARMS:
                self.data.ctrl[self.scene.actuators[arm]] = np.deg2rad(point[arm + '_joints_deg'])
                # Installed i2rt JointMapper uses inverse linear command/readback
                # scales. Google's stock Pro preload offset is not this mapping.
                self.data.ctrl[self.model.actuator(arm + '_gripper').id] = point[arm + '_gripper'] * FINGER_TRAVEL_M
            mujoco.mj_step(self.model, self.data, nstep=self.steps_per_command)
            self.cursor += 1
            if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
                raise RuntimeError('Nonfinite simulated state; no controller replay')
            if self.on_step is not None: self.on_step(self, point)
        self._settle_joints(points[-1])
        return self._measurements()

    def _settle_joints(self, final):
        # Existing i2rt_bimanual_adapter.execute defaults: .02rad joint error,
        #5s deadline and .35s continuously settled. Gripper contact can prevent
        # reaching a closed position; do not add an opening-error requirement.
        target=np.concatenate([np.deg2rad(final[arm+'_joints_deg']) for arm in ARMS])
        indices=[index for arm in ARMS for index in self.scene.arm_qpos[arm]]
        started=float(self.data.time);settled_since=None
        while float(self.data.time)-started<5.:
            if np.max(np.abs(self.data.qpos[indices]-target))<=.02:
                if settled_since is None:settled_since=float(self.data.time)
                if float(self.data.time)-settled_since>=.35:
                    self.packets[-1]['settled_at_sim_s']=float(self.data.time)
                    return
            else:settled_since=None
            mujoco.mj_step(self.model,self.data,nstep=self.steps_per_command)
            if not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all():
                raise RuntimeError('Nonfinite simulated settling state; no controller replay')
            if self.on_step is not None:self.on_step(self,None)
        raise RuntimeError('Simulated joints did not settle within the native5second allowance; no controller replay')

    def step(self, commands): return self.apply(commands, .1)

    def observe(self):
        if self.closed: raise RuntimeError('Simulated DeviceLayer has ended')
        return self._measurements()

    def end_stepping(self):
        if self.renderer is not None:
            self.renderer.close(); self.renderer = None
        self.closed = True
