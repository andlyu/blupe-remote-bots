"""Untrusted container entrypoint. No network, model key or hardware access."""
import contextlib
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0, '/workspace/controller-runtime')
from yam1_scene import Yam1Scene
from yam1_environment import RpcDeviceLayer, Yam1Environment


def main():
    # The host stages this immutable task configuration before starting the
    # container. The entire container remains untrusted at the host boundary.
    config = json.loads(Path('/workspace/controller-runtime/config.json').read_text())
    scene = Yam1Scene(config['runner_root'], config['gripper_dir'], config['calibration'])
    protocol = sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        spec = importlib.util.spec_from_file_location('generated_controller', '/workspace/controller.py')
        controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
        if not callable(getattr(controller, 'run', None)):
            raise ValueError('controller.py must define run(env)')
    protocol.write(json.dumps(dict(kind='ready', protocol=1))+'\n'); protocol.flush()
    layer = RpcDeviceLayer(sys.stdin, protocol, scene.safety)
    env = Yam1Environment(scene, layer, config['skills_root'])
    # Ordinary generated print() calls are diagnostics, never protocol packets.
    with contextlib.redirect_stdout(sys.stderr):
        controller.run(env)
    env.close()


if __name__ == '__main__': main()
