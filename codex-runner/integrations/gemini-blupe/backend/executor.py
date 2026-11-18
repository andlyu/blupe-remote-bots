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

try:
    from .simulation_artifacts import input_snapshot, retain_execution, write_private
except ImportError:
    from simulation_artifacts import input_snapshot, retain_execution, write_private


class SimulationExecutor:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.engine = os.environ.get('GEMINI_CONTAINER_ENGINE', 'podman')
        self.image = os.environ.get('GEMINI_SIM_IMAGE', '')
        self.variant = os.environ.get('GEMINI_SIM_VARIANT', 'yam1')
        self.container = 'gemini-sim-' + uuid.uuid4().hex
        self.cleanup_confirmed = False
        self.last_execution = None
        self.active_invocation = False

    @staticmethod
    def configured():
        return bool(shutil.which(os.environ.get('GEMINI_CONTAINER_ENGINE', 'podman'))
                    and re.fullmatch(r'sha256:[a-f0-9]{64}', os.environ.get('GEMINI_SIM_IMAGE', ''))
                    and os.environ.get('GEMINI_SIM_VARIANT', 'yam1') in ('yam1','reference'))

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
                '--workdir=/workspace', '--env=HOME=/tmp', '--env=GEMINI_SIM_VARIANT='+self.variant, self.image]

    async def stop(self):
        if self.cleanup_confirmed and not self.active_invocation:return
        self.cleanup_confirmed = False
        process = await asyncio.create_subprocess_exec(
            self.engine, 'rm', '--force', '--time=1', self.container,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:await asyncio.wait_for(process.wait(),timeout=6)
        except TimeoutError:
            process.kill();await process.wait()
            raise RuntimeError('Simulation container removal timed out; handoff is unverified')
        exists=await asyncio.create_subprocess_exec(
            self.engine,'container','exists',self.container,
            stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:code=await asyncio.wait_for(exists.wait(),timeout=3)
        except TimeoutError:
            exists.kill();await exists.wait()
            raise RuntimeError('Simulation container cleanup could not be confirmed')
        self.cleanup_confirmed=code==1
        if not self.cleanup_confirmed:
            raise RuntimeError('Simulation container cleanup could not be confirmed')
        self.active_invocation=False

    async def run(self, timeout_s=90):
        if self.active_invocation:
            raise RuntimeError('Previous simulation cleanup is unverified; no new execution started')
        before=input_snapshot(self.workspace,self.variant)
        self.last_execution=None
        # Remove only the previous outputs of this run before another attempt.
        for name in ('simulation.mp4', 'report.json', 'commands.json'):
            path = self.workspace / name
            if path.exists() or path.is_symlink():
                path.unlink()
        process = await asyncio.create_subprocess_exec(
            *self.command(), stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT)
        self.active_invocation=True
        output = bytearray()
        async def consume():
            while chunk := await process.stdout.read(8192):
                output.extend(chunk)
                if len(output) > 64000:
                    del output[:-64000]
            await process.wait()
        failure=None
        try:
            await asyncio.wait_for(consume(), timeout=timeout_s)
        except BaseException as exc:
            failure=exc
        finally:
            try:await asyncio.shield(self.stop())
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
        log = output.decode(errors='replace')
        write_private(self.workspace/'simulation.log',log.encode())
        self.last_execution,report=retain_execution(
            self.workspace,before,image=self.image,variant=self.variant,
            exit_code=process.returncode,log=log,cleanup_confirmed=self.cleanup_confirmed)
        if failure is not None:raise failure
        return dict(exit_code=process.returncode, output=log[-12000:],
                    report=report,execution=self.last_execution)
