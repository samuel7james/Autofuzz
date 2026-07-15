"""Unit tests for protocol fuzzing crash classification (Phase 5)."""

from __future__ import annotations

import asyncio

from autofuzz.protocol_fuzzing.crash_classifier import FaultKind, FuzzAttempt, classify, to_finding


def _attempt(exception: BaseException | None) -> FuzzAttempt:
    return FuzzAttempt(test_id=1, target="127.0.0.1:21", sequence=["USER a"], exception=exception)


def test_no_exception_classifies_as_none() -> None:
    assert classify(_attempt(None)) == FaultKind.NONE


def test_timeout_error_classifies_as_timeout() -> None:
    assert classify(_attempt(TimeoutError())) == FaultKind.TIMEOUT


def test_asyncio_timeout_error_classifies_as_timeout() -> None:
    assert classify(_attempt(asyncio.TimeoutError())) == FaultKind.TIMEOUT


def test_connection_refused_classifies_as_rejected() -> None:
    assert classify(_attempt(ConnectionRefusedError())) == FaultKind.REJECTED


def test_connection_reset_classifies_as_crash() -> None:
    assert classify(_attempt(ConnectionResetError())) == FaultKind.CRASH


def test_broken_pipe_classifies_as_crash() -> None:
    assert classify(_attempt(BrokenPipeError())) == FaultKind.CRASH


def test_eof_error_classifies_as_crash() -> None:
    assert classify(_attempt(EOFError())) == FaultKind.CRASH


def test_unrecognized_exception_defaults_to_crash() -> None:
    assert classify(_attempt(ValueError("weird"))) == FaultKind.CRASH


def test_to_finding_returns_none_for_no_fault() -> None:
    assert to_finding(_attempt(None), FaultKind.NONE) is None


def test_to_finding_returns_none_for_timeout() -> None:
    assert to_finding(_attempt(TimeoutError()), FaultKind.TIMEOUT) is None


def test_to_finding_returns_none_for_rejected() -> None:
    assert to_finding(_attempt(ConnectionRefusedError()), FaultKind.REJECTED) is None


def test_to_finding_produces_a_finding_for_a_crash() -> None:
    attempt = _attempt(ConnectionResetError())

    finding = to_finding(attempt, FaultKind.CRASH)

    assert finding is not None
    assert finding.target == "127.0.0.1:21"
    assert finding.metadata["fault_kind"] == "crash"
    assert finding.metadata["test_id"] == 1
