"""Isolated common-controller rollout for the adapted YAM1 scene.

station.json is staged by the trusted host, not inferred by the controller.
The physics/camera limitations are always retained with the actual replay.
"""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

import imageio.v2 as imageio

RUNNER_ROOT = Path(os.environ.get('GEMINI_RUNNER_ROOT', '/opt/runner'))
ASSETS = Path(os.environ.get('GEMINI_INSTALLED_ASSETS', '/opt/gemini/assets/linear4310'))
SKILLS = Path(os.environ.get('GEMINI_SKILLS_ROOT', '/opt/robotics/plugins/robotics/skills'))
sys.path.insert(0, str(RUNNER_ROOT / 'src'))
from yam1_scene import Yam1Scene
from yam1_environment import Yam1Environment
from yam1_simulation import SimulatedDeviceLayer


def main():
    started = time.monotonic()
    writer = None
    layer = None
    scene = None
    frames = 0
    error = None
    station_path = Path('/workspace/station.json')
    controller_path = Path('/workspace/controller.py')
    station_bytes = station_path.read_bytes()
    station = json.loads(station_bytes)
    observation = station['observation']
    calibration = station['calibration']
    try:
        scene = Yam1Scene(RUNNER_ROOT, ASSETS, calibration)
        arms = {arm:[math.radians(v) for v in observation[arm+'_joints_deg']] for arm in ('left','right')}
        scene.set_configuration(arms, {arm:observation[arm+'_gripper'] for arm in ('left','right')})
        def record(device, point):
            nonlocal writer, frames
            if frames >= 600:
                raise RuntimeError('Simulation reached the existing 60-second recording budget')
            if writer is None:
                writer = imageio.get_writer('/workspace/simulation.mp4', fps=10, macro_block_size=2)
            writer.append_data(device.render('top', width=320, height=180))
            frames += 1
        layer = SimulatedDeviceLayer(scene, RUNNER_ROOT, on_step=record)
        env = Yam1Environment(scene, layer, SKILLS)
        spec = importlib.util.spec_from_file_location('generated_controller', controller_path)
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        controller.run(env)
        if frames == 0:
            raise RuntimeError('Controller produced no simulated steps')
    except Exception as exc:
        error = type(exc).__name__ + ': ' + str(exc)[:1000]
        raise
    finally:
        if writer is not None: writer.close()
        if layer is not None: layer.end_stepping()
        report = scene.receipt() if scene is not None else dict(physical=False, task_success_verified=False)
        report.update(scope='Adapted bimanual YAM1 common-controller simulation; contact/task-scene qualification pending',
                      controller_completed=error is None, error=error, frames=frames,
                      controller_sha256=hashlib.sha256(controller_path.read_bytes()).hexdigest(),
                      station_snapshot_sha256=hashlib.sha256(station_bytes).hexdigest(),
                      initial_observation_source=observation.get('source'),
                      initial_observed_at=observation.get('observed_at'),
                      simulated_seconds=None if layer is None else float(layer.data.time),
                      wall_seconds=round(time.monotonic()-started,3),
                      video_camera='top', video_resolution=[320,180], video_fps=10,
                      completion_semantics='Simulated packet integration; native physical settling/contact qualification remains open')
        if layer is not None:
            report['warning_counts'] = {str(i):int(w.number) for i,w in enumerate(layer.data.warning) if w.number}
            report['final_simulated_observation'] = layer.observation()
        Path('/workspace/report.json').write_text(json.dumps(report,indent=2)+'\n')
        Path('/workspace/commands.json').write_text(json.dumps([] if layer is None else layer.packets)+'\n')


if __name__ == '__main__': main()
