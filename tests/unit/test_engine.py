"""Unit tests for ProtocolFuzzingEngine construction (Phase 5).

Full run() behavior (real network I/O) is covered by
tests/integration/test_protocol_engine.py.
"""

from __future__ import annotations

import pytest

from autofuzz.core.config import ProtocolEngineConfig, SchedulerConfig
from autofuzz.core.errors import EngineError
from autofuzz.protocol_fuzzing.engine import ProtocolFuzzingEngine


def test_unsupported_adapter_raises_engine_error() -> None:
    protocol_config = ProtocolEngineConfig(adapter="smtp")

    with pytest.raises(EngineError, match="smtp"):
        ProtocolFuzzingEngine(protocol_config, SchedulerConfig())
