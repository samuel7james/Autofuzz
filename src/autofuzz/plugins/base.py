"""Shared plugin and finding contracts used by both engines.

``Finding`` is the universal output unit: a web assessment observation and
a protocol fuzzing crash both produce Findings, so the reporting engine can
render both without engine-specific special-casing. ``Plugin`` is the base
every assessment module - web or protocol - implements the same way.

Plugins are deliberately synchronous and side-effect-free: they analyze
data an engine already collected (a fetched page, a fuzzing attempt's
outcome) rather than performing their own I/O. That keeps "passive
analysis" literal - no plugin makes its own network requests - and makes
every plugin trivially unit-testable as a pure function of its context.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Finding:
    """One observation produced by a plugin."""

    plugin_id: str
    title: str
    severity: Severity
    description: str
    target: str
    evidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe plain dict (severity as its string value)."""
        data = asdict(self)
        data["severity"] = self.severity.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(**{**data, "severity": Severity(data["severity"])})


@dataclass(frozen=True, slots=True)
class PluginMetadata:
    id: str
    name: str
    description: str
    engine: str  # "web" or "proto"


ContextT = TypeVar("ContextT")


class Plugin(ABC, Generic[ContextT]):
    """A self-contained, synchronous assessment unit."""

    metadata: PluginMetadata

    @abstractmethod
    def applies_to(self, context: ContextT) -> bool:
        """Return True if this plugin should run against ``context``."""

    @abstractmethod
    def run(self, context: ContextT) -> list[Finding]:
        """Analyze ``context``, returning zero or more Findings."""

    def configure(self, options: dict[str, Any]) -> None:
        """Apply plugin-specific options from a ScanProfile. No-op by default."""
