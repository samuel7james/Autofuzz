"""Unit tests for RiskScore and ScanReport (Phase 6)."""

from __future__ import annotations

from autofuzz.plugins.base import Finding, Severity
from autofuzz.reporting.models import RiskScore, ScanReport


def _finding(severity: Severity, title: str = "f") -> Finding:
    return Finding(
        plugin_id="test.plugin", title=title, severity=severity, description="d", target="t"
    )


def test_risk_score_from_no_findings() -> None:
    risk = RiskScore.from_findings([])

    assert risk.score == 0
    assert risk.max_severity is None
    assert all(count == 0 for count in risk.counts_by_severity.values())


def test_risk_score_weights_higher_severities_more() -> None:
    low_risk = RiskScore.from_findings([_finding(Severity.LOW)])
    high_risk = RiskScore.from_findings([_finding(Severity.HIGH)])

    assert high_risk.score > low_risk.score


def test_risk_score_max_severity_tracks_the_worst_finding() -> None:
    risk = RiskScore.from_findings([_finding(Severity.LOW), _finding(Severity.CRITICAL)])

    assert risk.max_severity == Severity.CRITICAL


def test_risk_score_counts_by_severity() -> None:
    findings = [_finding(Severity.HIGH), _finding(Severity.HIGH), _finding(Severity.LOW)]
    risk = RiskScore.from_findings(findings)

    assert risk.counts_by_severity[Severity.HIGH] == 2
    assert risk.counts_by_severity[Severity.LOW] == 1
    assert risk.counts_by_severity[Severity.INFO] == 0


def test_scan_report_create_starts_incomplete() -> None:
    report = ScanReport.create(scan_id="abc123", engine="web", target="https://x", profile_name="p")

    assert report.completed_at is None
    assert report.findings == []
    assert report.started_at


def test_scan_report_complete_sets_completed_at() -> None:
    report = ScanReport.create(scan_id="abc123", engine="web", target="https://x", profile_name="p")

    report.complete()

    assert report.completed_at is not None


def test_scan_report_risk_reflects_its_findings() -> None:
    report = ScanReport.create(
        scan_id="abc123", engine="proto", target="1.2.3.4:21", profile_name="p"
    )
    report.findings = [_finding(Severity.CRITICAL)]

    assert report.risk.max_severity == Severity.CRITICAL
