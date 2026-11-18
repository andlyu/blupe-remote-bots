"""Run generated controllers in a separate, key-free rootless container.

Podman4.9.3 run contract: network=none, read-only image, keep-id and a
per-run mount. This module never evaluates generated code in the API process.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import uuid


class SimulationExecutor:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.engine = os.environ.get('GEMINI_CONTAINER_ENGINE', 'podman')
        self.image = os.environ.get('GEMINI_SIM_IMAGE', '')
        self.container = 'gemini-sim-' + uuid.uuid4().hex

    @staticmethod
    def configured():
        return bool(shutil.which(os.environ.get('GEMINI_CONTAINER_ENGINE', 'podman'))
                    and re.fullmatch(r'sha256:[a-f0-9]{64}', os.environ.get('GEMINI_SIM_IMAGE', '')))

    def command(self):
        if not self.configured() or not self.workspace.is_dir() or self.workspace.is_symlink():
            raise RuntimeError('An immutable simulation image and isolated executor are required')
        return [self.engine, 'run', '--pull=never', '--rm', '--name', self.container,
                '--network=none', '--read-only', '--cap-drop=ALL',
                '--security-opt=no-new-privileges', '--userns=keep-id',
                '--pids-limit=128', '--memory=1536m', '--cpus=1',
                '--ulimit=fsize=134217728:134217728',
                '--tmpfs=/tmp:rw,nosuid,nodev,size=256m',
                '--volume', str(self.workspace) + ':/workspace:rw',
                '--workdir=/workspace', '--env=HOME=/tmp', self.image]

    async def stop(self):
        process = await asyncio.create_subprocess_exec(
            self.engine, 'rm', '--force', '--time=1', self.container,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await process.wait()

    async def run(self, timeout_s=90):
        # Remove only the previous outputs of this run before another attempt.
        for name in ('simulation.mp4', 'report.json', 'commands.json'):
            path = self.workspace / name
            if path.exists() or path.is_symlink():
                path.unlink()
        process = await asyncio.create_subprocess_exec(
            *self.command(), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        output = bytearray()
        async def consume():
            while chunk := await process.stdout.read(8192):
                output.extend(chunk)
                if len(output) > 64000:
                    del output[:-64000]
            await process.wait()
        try:
            await asyncio.wait_for(consume(), timeout=timeout_s)
        finally:
            await asyncio.shield(self.stop())
            if process.returncode is None:
                process.kill()
                await process.wait()
        log = output.decode(errors='replace')
        fd = os.open(self.workspace / 'simulation.log', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as file:
            file.write(log)
        report = self.workspace / 'report.json'
        return dict(exit_code=process.returncode, output=log[-12000:],
                    report=json.loads(report.read_text()) if report.is_file() and not report.is_symlink() and report.stat().st_size < 64000 else None)
