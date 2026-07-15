"""Report data models: RiskScore and ScanReport.

``Finding`` already lives in ``plugins/base.py`` (Phase 5) as the universal
output unit both engines produce. This module adds the container/summary
types that turn a list of Findings into something renderable: an aggregate
risk score and a full scan report with metadata, timing, and statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from autofuzz.plugins.base import Finding, Severity

_SEVERITY_WEIGHTS: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 4,
    Severity.HIGH: 9,
    Severity.CRITICAL: 16,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class RiskScore:
    """A simple, explainable aggregate score derived from finding severities."""

    score: int
    max_severity: Severity | None
    counts_by_severity: dict[Severity, int]

    @classmethod
    def from_findings(cls, findings: list[Finding]) -> RiskScore:
        counts: dict[Severity, int] = dict.fromkeys(Severity, 0)
        for finding in findings:
            counts[finding.severity] += 1
        score = sum(_SEVERITY_WEIGHTS[severity] * n for severity, n in counts.items())
        present = [severity for severity, n in counts.items() if n > 0]
        max_severity = max(present, key=lambda s: _SEVERITY_WEIGHTS[s]) if present else None
        return cls(score=score, max_severity=max_severity, counts_by_severity=counts)


@dataclass
class ScanReport:
    """A complete, renderable record of one scan."""

    scan_id: str
    engine: str
    target: str
    profile_name: str
    started_at: str = field(default_factory=_now)
    completed_at: str | None = None
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def risk(self) -> RiskScore:
        return RiskScore.from_findings(self.findings)

    @classmethod
    def create(cls, *, scan_id: str, engine: str, target: str, profile_name: str) -> ScanReport:
        return cls(scan_id=scan_id, engine=engine, target=target, profile_name=profile_name)

    def complete(self) -> None:
        self.completed_at = _now()
