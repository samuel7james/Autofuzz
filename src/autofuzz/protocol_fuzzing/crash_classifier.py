"""Crash classification for protocol fuzzing attempts.

Replaces v1's "any exception is a CRASH" logic, which flagged ordinary
timeouts and protocol-level rejections the same way as an actual target
fault. This module gives fuzzing attempts an explicit taxonomy and turns
classified crashes into ``Finding``s, so protocol fuzzing output flows
through the same reporting pipeline as web assessment output.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from autofuzz.plugins.base import Finding, Severity

_TIMEOUT_EXCEPTIONS: tuple[type[BaseException], ...] = (TimeoutError, asyncio.TimeoutError)
_CRASH_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    EOFError,
    OSError,
)


class FaultKind(str, Enum):
    NONE = "none"  # got a normal response
    TIMEOUT = "timeout"  # no response within the configured timeout
    REJECTED = "rejected"  # connection actively refused - target alive, rejected us
    CRASH = "crash"  # connection dropped mid-sequence / unexpected disconnect


@dataclass(frozen=True, slots=True)
class FuzzAttempt:
    """One fuzzing attempt's outcome: the mutated sequence sent and what happened."""

    test_id: int
    target: str
    sequence: list[str] = field(default_factory=list)
    response: str | None = None
    exception: BaseException | None = None


def classify(attempt: FuzzAttempt) -> FaultKind:
    """Classify a fuzzing attempt's outcome, distinguishing a real fault
    from an ordinary timeout or a deliberate protocol-level rejection."""
    exc = attempt.exception
    if exc is None:
        return FaultKind.NONE
    if isinstance(exc, _TIMEOUT_EXCEPTIONS):
        return FaultKind.TIMEOUT
    if isinstance(exc, ConnectionRefusedError):
        return FaultKind.REJECTED
    if isinstance(exc, _CRASH_EXCEPTIONS):
        return FaultKind.CRASH
    return FaultKind.CRASH


def to_finding(attempt: FuzzAttempt, fault: FaultKind) -> Finding | None:
    """Turn a classified attempt into a Finding, or None if there's nothing
    worth reporting (a normal response, a timeout, or a plain rejection)."""
    if fault in (FaultKind.NONE, FaultKind.TIMEOUT, FaultKind.REJECTED):
        return None
    return Finding(
        plugin_id="protocol-fuzzing.crash-classifier",
        title="Target crashed or disconnected unexpectedly during fuzzing",
        severity=Severity.HIGH,
        description=(
            "The target closed the connection or raised an unexpected error while "
            "processing a mutated command sequence, suggesting a real fault rather "
            "than a timeout or a deliberate protocol-level rejection."
        ),
        target=attempt.target,
        evidence=f"sequence={attempt.sequence!r} error={attempt.exception!r}",
        metadata={"test_id": attempt.test_id, "fault_kind": fault.value},
    )
