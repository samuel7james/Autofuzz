"""Integration tests: FTP adapter + Protocol Fuzzing Engine against a real
local asyncio TCP server (not mocked).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import pytest_asyncio

from autofuzz.core.config import ProtocolEngineConfig, SchedulerConfig
from autofuzz.protocol_fuzzing.adapters.ftp import send_sequence
from autofuzz.protocol_fuzzing.crash_classifier import FaultKind, classify
from autofuzz.protocol_fuzzing.engine import ProtocolFuzzingEngine

_CRASH_THRESHOLD = 500


async def _handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """A minimal fake FTP-ish server: answers short commands with '200 OK',
    but drops the connection without responding once it has received more
    than _CRASH_THRESHOLD cumulative bytes on one connection - simulating a
    naive server that chokes on an oversized/malformed payload."""
    writer.write(b"220 fake FTP ready\r\n")
    await writer.drain()
    total_received = 0
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            total_received += len(chunk)
            if total_received > _CRASH_THRESHOLD:
                writer.close()
                return
            writer.write(b"200 OK\r\n")
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        if not writer.is_closing():
            writer.close()


@pytest_asyncio.fixture
async def fake_ftp_server() -> AsyncIterator[tuple[str, int]]:
    server = await asyncio.start_server(_handle_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    serve_task = asyncio.create_task(server.serve_forever())
    try:
        yield host, port
    finally:
        serve_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await serve_task
        server.close()
        await server.wait_closed()


async def test_send_sequence_succeeds_against_a_healthy_server(
    fake_ftp_server: tuple[str, int],
) -> None:
    host, port = fake_ftp_server

    attempt = await send_sequence(host, port, ["SHORT"], test_id=1, timeout=2.0)

    assert attempt.exception is None
    assert attempt.response == "200 OK\r\n"
    assert classify(attempt) == FaultKind.NONE


async def test_send_sequence_captures_a_dropped_connection_as_a_crash(
    fake_ftp_server: tuple[str, int],
) -> None:
    host, port = fake_ftp_server
    huge_command = "A" * (_CRASH_THRESHOLD + 100)

    attempt = await send_sequence(host, port, [huge_command], test_id=2, timeout=2.0)

    assert attempt.exception is not None
    assert classify(attempt) == FaultKind.CRASH


async def test_send_sequence_against_a_closed_port_is_not_a_crash() -> None:
    probe = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    host, port = probe.sockets[0].getsockname()[:2]
    probe.close()
    await probe.wait_closed()

    attempt = await send_sequence(host, port, ["USER a"], test_id=3, timeout=2.0)

    # Whether an unreachable port surfaces as an immediate RST
    # (ConnectionRefusedError -> REJECTED) or a silently dropped SYN
    # (-> TIMEOUT) depends on the OS/network stack, not on AutoFuzz. Either
    # is correct here; REJECTED's exact classification is covered directly
    # in tests/unit/test_crash_classifier.py. What matters is that neither
    # is misclassified as a target CRASH.
    assert classify(attempt) in (FaultKind.REJECTED, FaultKind.TIMEOUT)


async def test_engine_run_produces_crash_findings(fake_ftp_server: tuple[str, int]) -> None:
    host, port = fake_ftp_server
    protocol_config = ProtocolEngineConfig(
        adapter="ftp", target_host=host, target_port=port, iterations=3
    )
    scheduler_config = SchedulerConfig(
        concurrency=3, rate_limit_per_second=1000, max_retries=0, request_timeout_seconds=2.0
    )
    engine = ProtocolFuzzingEngine(protocol_config, scheduler_config)

    findings = await engine.run()

    # Every mutator inflates "USER vulnftp" well past _CRASH_THRESHOLD, so
    # the first FSM command of every attempt should trip the fake server's
    # crash simulation.
    assert len(findings) == 3
    assert all(f.plugin_id == "protocol-fuzzing.crash-classifier" for f in findings)
    assert all(f.severity.value == "high" for f in findings)


class _FlakyTargetController:
    """Reports the target down for the first check, then alive - so a run
    should call recover() exactly once and continue."""

    def __init__(self) -> None:
        self.is_alive_calls = 0
        self.recover_calls = 0

    async def is_alive(self) -> bool:
        self.is_alive_calls += 1
        return self.is_alive_calls > 1

    async def recover(self) -> None:
        self.recover_calls += 1


async def test_engine_recovers_a_down_target_before_continuing(
    fake_ftp_server: tuple[str, int],
) -> None:
    host, port = fake_ftp_server
    protocol_config = ProtocolEngineConfig(
        adapter="ftp", target_host=host, target_port=port, iterations=1
    )
    scheduler_config = SchedulerConfig(
        concurrency=1, rate_limit_per_second=1000, max_retries=0, request_timeout_seconds=2.0
    )
    controller = _FlakyTargetController()
    engine = ProtocolFuzzingEngine(protocol_config, scheduler_config, controller)

    findings = await engine.run()

    assert controller.recover_calls == 1
    assert len(findings) == 1


async def test_engine_reports_progress_per_chunk(fake_ftp_server: tuple[str, int]) -> None:
    host, port = fake_ftp_server
    protocol_config = ProtocolEngineConfig(
        adapter="ftp", target_host=host, target_port=port, iterations=4
    )
    scheduler_config = SchedulerConfig(
        concurrency=2, rate_limit_per_second=1000, max_retries=0, request_timeout_seconds=2.0
    )
    progress_calls: list[tuple[int, int, int]] = []

    def on_progress(completed: int, total: int, findings_so_far: list[object]) -> None:
        progress_calls.append((completed, total, len(findings_so_far)))

    engine = ProtocolFuzzingEngine(protocol_config, scheduler_config, on_progress=on_progress)
    findings = await engine.run()

    # 4 iterations at concurrency 2 -> two chunks -> two progress callbacks,
    # and the findings_so_far passed on the last callback matches the
    # engine's final return value (it's the cumulative list, not a delta).
    assert [c[0] for c in progress_calls] == [2, 4]
    assert [c[1] for c in progress_calls] == [4, 4]
    assert progress_calls[-1][2] == len(findings)


async def test_engine_resumes_from_start_iteration(fake_ftp_server: tuple[str, int]) -> None:
    host, port = fake_ftp_server
    protocol_config = ProtocolEngineConfig(
        adapter="ftp", target_host=host, target_port=port, iterations=4
    )
    scheduler_config = SchedulerConfig(
        concurrency=2, rate_limit_per_second=1000, max_retries=0, request_timeout_seconds=2.0
    )
    progress_calls: list[int] = []

    def on_progress(completed: int, _total: int, _findings: list[object]) -> None:
        progress_calls.append(completed)

    engine = ProtocolFuzzingEngine(protocol_config, scheduler_config, on_progress=on_progress)

    await engine.run(start_iteration=2)

    # Resuming from iteration 2 of 4 should only run the remaining 2
    # attempts (one chunk), reported as completed=4 - never re-visiting
    # iterations 0-1.
    assert progress_calls == [4]
