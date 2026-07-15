"""Protocol Fuzzing Engine: orchestrates an FSM-guided, mutation-driven
fuzzing run against a live target - v1's successor.

Ties together the scheduler (Phase 3), the mutation corpus and FSM, the
transport adapter, and crash classification (this phase) into one runnable
scan, replacing v1's synchronous ``fuzz()`` loop. Attempts run concurrently
in chunks sized to ``scheduler.concurrency``; target liveness is checked
between chunks so a down target gets a chance to recover before the next
batch, mirroring v1's check-before-each-attempt behavior without defeating
real concurrency.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from autofuzz.core.config import ProtocolEngineConfig, SchedulerConfig
from autofuzz.core.errors import EngineError
from autofuzz.core.logging import get_logger
from autofuzz.core.scheduler import WorkerPool
from autofuzz.core.target_controller import NoOpTargetController, TargetController
from autofuzz.plugins.base import Finding
from autofuzz.protocol_fuzzing.adapters.ftp import send_sequence
from autofuzz.protocol_fuzzing.crash_classifier import classify, to_finding
from autofuzz.protocol_fuzzing.fsm import ProtocolFsm
from autofuzz.protocol_fuzzing.mutators.strategies import mutate

log = get_logger(__name__)

_FTP_DEFAULT_SEQUENCE = ["USER vulnftp", "PASS 1234", "PWD", "TYPE A", "LIST", "QUIT"]

_DEFAULT_SEQUENCES: dict[str, list[str]] = {"ftp": _FTP_DEFAULT_SEQUENCE}


class ProtocolFuzzingEngine:
    """Runs ``protocol_config.iterations`` mutated attempts against a target,
    recovering it via ``target_controller`` when it goes down, and returns
    the Findings produced by any classified crashes."""

    def __init__(
        self,
        protocol_config: ProtocolEngineConfig,
        scheduler_config: SchedulerConfig,
        target_controller: TargetController | None = None,
    ) -> None:
        if protocol_config.adapter not in _DEFAULT_SEQUENCES:
            raise EngineError(f"Unsupported protocol adapter: {protocol_config.adapter!r}")
        self._protocol_config = protocol_config
        self._scheduler_config = scheduler_config
        self._target_controller = target_controller or NoOpTargetController()
        self._fsm = ProtocolFsm.from_commands(_DEFAULT_SEQUENCES[protocol_config.adapter])

    async def run(self) -> list[Finding]:
        findings: list[Finding] = []
        iterations = self._protocol_config.iterations
        chunk_size = self._scheduler_config.concurrency

        for chunk_start in range(0, iterations, chunk_size):
            if not await self._target_controller.is_alive():
                log.warning("target_down_recovering", target=self._target())
                await self._target_controller.recover()

            chunk_len = min(chunk_size, iterations - chunk_start)
            pool: WorkerPool[Finding | None] = WorkerPool(self._scheduler_config)
            jobs = [self._attempt_job(chunk_start + i) for i in range(chunk_len)]
            results = await pool.run_all(jobs)

            for result in results:
                if isinstance(result, BaseException):
                    log.warning("fuzz_attempt_failed_unexpectedly", error=str(result))
                    continue
                if result is not None:
                    findings.append(result)

        return findings

    def _target(self) -> str:
        return f"{self._protocol_config.target_host}:{self._protocol_config.target_port}"

    def _attempt_job(self, test_id: int) -> Callable[[], Awaitable[Finding | None]]:
        async def job() -> Finding | None:
            sequence = [mutate(cmd) for cmd in self._fsm.commands()]
            attempt = await send_sequence(
                self._protocol_config.target_host,
                self._protocol_config.target_port,
                sequence,
                test_id=test_id,
                timeout=self._scheduler_config.request_timeout_seconds,
            )
            return to_finding(attempt, classify(attempt))

        return job
