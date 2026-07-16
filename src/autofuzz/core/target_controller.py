"""Target liveness checking and recovery.

A pluggable interface: any container name, not a hardcoded one, and any
number of controller implementations. Recovery defaults to a no-op: a scan
against a target the tool doesn't provision itself (a client's
environment, a bare URL) must never be "recovered" without an operator
opting into a specific, scoped controller.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from autofuzz.core.errors import TargetError
from autofuzz.core.logging import get_logger

log = get_logger(__name__)


class TargetController(Protocol):
    """Checks whether a target is alive and can attempt to recover it."""

    async def is_alive(self) -> bool: ...

    async def recover(self) -> None: ...


class NoOpTargetController:
    """Default controller: reports the target as always alive, never restarts anything."""

    async def is_alive(self) -> bool:
        return True

    async def recover(self) -> None:
        log.warning("recover_called_on_noop_controller", detail="no action taken")


class DockerTargetController:
    """Recovers a named Docker container that AutoFuzz provisioned itself.

    Takes any container name (not a hardcoded one), uses async subprocess
    calls instead of blocking ones, and checks liveness via
    ``docker inspect`` instead of assuming the caller already knows.
    """

    def __init__(self, container_name: str, *, restart_grace_period: float = 5.0) -> None:
        self._container_name = container_name
        self._restart_grace_period = restart_grace_period
        self._restart_count = 0

    @property
    def restart_count(self) -> int:
        return self._restart_count

    async def is_alive(self) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "inspect",
            "-f",
            "{{.State.Running}}",
            self._container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return proc.returncode == 0 and stdout.strip() == b"true"

    async def recover(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "restart",
            self._container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise TargetError(
                f"Failed to restart container {self._container_name!r}: "
                f"{stderr.decode(errors='replace').strip()}"
            )
        self._restart_count += 1
        log.info(
            "docker_container_restarted",
            container=self._container_name,
            restart_count=self._restart_count,
        )
        await asyncio.sleep(self._restart_grace_period)
