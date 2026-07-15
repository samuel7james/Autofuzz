"""Unit tests for TargetController implementations (Phase 3)."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from autofuzz.core.errors import TargetError
from autofuzz.core.target_controller import DockerTargetController, NoOpTargetController


def _fake_exec_factory(
    stdout: bytes, stderr: bytes, returncode: int
) -> Callable[..., Coroutine[Any, Any, AsyncMock]]:
    async def fake_exec(*_args: str, **_kwargs: object) -> AsyncMock:
        proc = AsyncMock()
        proc.communicate.return_value = (stdout, stderr)
        proc.returncode = returncode
        return proc

    return fake_exec


async def test_noop_controller_is_always_alive() -> None:
    controller = NoOpTargetController()
    assert await controller.is_alive() is True


async def test_noop_controller_recover_does_not_raise() -> None:
    controller = NoOpTargetController()
    await controller.recover()


async def test_docker_controller_is_alive_true() -> None:
    controller = DockerTargetController("test-container")
    fake_exec = _fake_exec_factory(b"true\n", b"", 0)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        assert await controller.is_alive() is True


async def test_docker_controller_is_alive_false_when_stopped() -> None:
    controller = DockerTargetController("test-container")
    fake_exec = _fake_exec_factory(b"false\n", b"", 0)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        assert await controller.is_alive() is False


async def test_docker_controller_recover_increments_restart_count() -> None:
    controller = DockerTargetController("test-container", restart_grace_period=0)
    fake_exec = _fake_exec_factory(b"", b"", 0)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec):
        await controller.recover()

    assert controller.restart_count == 1


async def test_docker_controller_recover_raises_target_error_on_failure() -> None:
    controller = DockerTargetController("test-container", restart_grace_period=0)
    fake_exec = _fake_exec_factory(b"", b"no such container", 1)

    with patch("asyncio.create_subprocess_exec", side_effect=fake_exec), pytest.raises(TargetError):
        await controller.recover()

    assert controller.restart_count == 0
