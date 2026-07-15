"""Markdown report renderer: executive summary + findings + statistics."""

from __future__ import annotations

from autofuzz.plugins.base import Finding, Severity
from autofuzz.reporting.models import ScanReport

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]


def _severity_rank(finding: Finding) -> int:
    return _SEVERITY_ORDER.index(finding.severity)


def render(report: ScanReport) -> str:
    risk = report.risk
    lines = [
        f"# AutoFuzz Scan Report: {report.profile_name}",
        "",
        "## Executive Summary",
        "",
        f"- **Engine:** {report.engine}",
        f"- **Target:** {report.target}",
        f"- **Scan ID:** {report.scan_id}",
        f"- **Started:** {report.started_at}",
        f"- **Completed:** {report.completed_at or 'in progress'}",
        f"- **Risk score:** {risk.score} "
        f"(highest severity: {risk.max_severity.value if risk.max_severity else 'none'})",
        f"- **Total findings:** {len(report.findings)}",
        "",
        "## Findings by Severity",
        "",
        "| Severity | Count |",
        "|---|---|",
    ]
    for severity in _SEVERITY_ORDER:
        lines.append(f"| {severity.value} | {risk.counts_by_severity.get(severity, 0)} |")

    lines += ["", "## Findings", ""]
    if not report.findings:
        lines.append("No findings.")
    else:
        for finding in sorted(report.findings, key=_severity_rank):
            lines += [
                f"### [{finding.severity.value.upper()}] {finding.title}",
                "",
                f"- **Plugin:** {finding.plugin_id}",
                f"- **Target:** {finding.target}",
                f"- **Discovered:** {finding.discovered_at}",
                "",
                finding.description,
                "",
            ]
            if finding.evidence:
                lines += ["**Evidence:**", "", "```", finding.evidence, "```", ""]

    lines += ["## Scan Statistics", ""]
    if report.stats:
        lines += ["| Metric | Value |", "|---|---|"]
        lines += [f"| {key} | {value} |" for key, value in report.stats.items()]
    else:
        lines.append("No statistics recorded.")

    return "\n".join(lines)
