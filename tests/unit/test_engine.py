"""Unit tests for ProtocolFuzzingEngine construction and adapter dispatch
(Phase 5/11). Full run() behavior against a real target (the FTP adapter
specifically) is covered by tests/integration/test_protocol_engine.py.
"""

from __future__ import annotations

import pytest

import autofuzz.protocol_fuzzing.engine as engine_module
from autofuzz.core.config import ProtocolEngineConfig, SchedulerConfig
from autofuzz.core.errors import EngineError
from autofuzz.protocol_fuzzing.crash_classifier import FuzzAttempt
from autofuzz.protocol_fuzzing.engine import ADAPTERS, ProtocolAdapter, ProtocolFuzzingEngine


def test_unsupported_adapter_raises_engine_error() -> None:
    protocol_config = ProtocolEngineConfig(adapter="smtp")

    with pytest.raises(EngineError, match="smtp"):
        ProtocolFuzzingEngine(protocol_config, SchedulerConfig())


async def test_run_dispatches_to_the_configured_adapters_send_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registered adapter's own send_sequence must actually be called -
    not just have its default_sequence used while the transport call stays
    hardcoded to another adapter (the bug this test guards against: the
    engine used to import and call ftp.send_sequence directly regardless
    of which adapter was configured)."""
    calls: list[tuple[str, int, list[str]]] = []

    async def fake_send_sequence(
        host: str, port: int, sequence: list[str], *, test_id: int, timeout: float
    ) -> FuzzAttempt:
        calls.append((host, port, sequence))
        return FuzzAttempt(test_id=test_id, target=f"{host}:{port}", sequence=sequence)

    monkeypatch.setitem(
        ADAPTERS,
        "fake",
        ProtocolAdapter(default_sequence=["HELLO"], send_sequence=fake_send_sequence),
    )
    monkeypatch.setattr(engine_module, "mutate", lambda cmd: cmd)  # deterministic for this test

    protocol_config = ProtocolEngineConfig(
        adapter="fake", target_host="127.0.0.1", target_port=9999, iterations=2
    )
    scheduler_config = SchedulerConfig(concurrency=2, rate_limit_per_second=1000, max_retries=0)
    engine = ProtocolFuzzingEngine(protocol_config, scheduler_config)

    findings = await engine.run()

    assert findings == []  # a clean FuzzAttempt with no exception -> no crash
    assert len(calls) == 2
    assert all(host == "127.0.0.1" and port == 9999 for host, port, _seq in calls)
    assert all(seq == ["HELLO"] for _host, _port, seq in calls)
