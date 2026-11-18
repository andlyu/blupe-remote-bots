"""Container-only entrypoint for the official reference scene.

This reference is explicitly not the matched bimanual BluPe YAM1 scene.
The same controller can be rerun after edits; no real devices are exposed.
"""
import importlib.util
import json
from pathlib import Path
import sys
import time

import imageio.v2 as imageio
import numpy as np

sys.path.insert(0, '/opt/robotics/plugins/robotics/skills/mujoco-playground/scripts')
from playground_sim2real import PlaygroundSim2Real


def main():
    started = time.monotonic()
    commands = []
    frames = 0
    env = None
    error = None
    writer = imageio.get_writer('/workspace/simulation.mp4', fps=10)
    try:
        env = PlaygroundSim2Real(robot='yam', mode='sim', control_period_s=.1, reset_to_hover=False)
        step = env.step_joint
        def recorded_step(q_arm, gripper=None):
            nonlocal frames
            if frames >= 600:
                raise RuntimeError('Reference simulation reached its 60-second recording limit')
            result = step(q_arm, gripper)
            commands.append(dict(q_arm_rad=np.asarray(q_arm).tolist(), gripper=gripper))
            writer.append_data(np.asarray(env.measurements['wrist_camera']))
            frames += 1
            return result
        env.step_joint = recorded_step
        spec = importlib.util.spec_from_file_location('generated_controller', '/workspace/controller.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        outcome = controller.run(env)
        if frames == 0:
            raise RuntimeError('Controller produced no simulated steps')
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)[:1000]
        raise
    finally:
        writer.close()
        if env is not None:
            env.close(park=False)
        report = dict(scope='Google official single-arm reference; bimanual YAM1 matching pending',
                      physical=False, task_success_verified=False, controller_completed=error is None,
                      error=error, frames=frames, simulated_seconds=frames * .1,
                      wall_seconds=round(time.monotonic() - started, 3))
        Path('/workspace/report.json').write_text(json.dumps(report, indent=2) + '\n')
        Path('/workspace/commands.json').write_text(json.dumps(commands) + '\n')


if __name__ == '__main__':
    main()
