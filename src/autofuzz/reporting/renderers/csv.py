"""CSV report renderer: one row per Finding."""

from __future__ import annotations

import csv
import io

from autofuzz.reporting.models import ScanReport

_FIELDNAMES = [
    "scan_id",
    "target",
    "plugin_id",
    "severity",
    "title",
    "description",
    "evidence",
    "discovered_at",
]


def render(report: ScanReport) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_FIELDNAMES)
    writer.writeheader()
    for finding in report.findings:
        writer.writerow(
            {
                "scan_id": report.scan_id,
                "target": finding.target,
                "plugin_id": finding.plugin_id,
                "severity": finding.severity.value,
                "title": finding.title,
                "description": finding.description,
                "evidence": finding.evidence,
                "discovered_at": finding.discovered_at,
            }
        )
    return buffer.getvalue()
