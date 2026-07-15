"""Unit tests for the report renderers: HTML, Markdown, JSON, CSV (Phase 6)."""

from __future__ import annotations

import csv
import io
import json

from autofuzz.plugins.base import Finding, Severity
from autofuzz.reporting.models import ScanReport
from autofuzz.reporting.renderers import csv as csv_renderer
from autofuzz.reporting.renderers import html as html_renderer
from autofuzz.reporting.renderers import json as json_renderer
from autofuzz.reporting.renderers import markdown as markdown_renderer


def _report(findings: list[Finding] | None = None) -> ScanReport:
    report = ScanReport.create(
        scan_id="scan123",
        engine="web",
        target="https://target.example",
        profile_name="test-profile",
    )
    report.findings = findings or []
    report.stats = {"pages_crawled": 5}
    report.complete()
    return report


def _finding(**overrides: object) -> Finding:
    fields: dict[str, object] = {
        "plugin_id": "web.missing-security-headers",
        "title": "Missing X-Frame-Options header",
        "severity": Severity.LOW,
        "description": "The response did not set an X-Frame-Options header.",
        "target": "https://target.example",
        "evidence": "Response headers: []",
        **overrides,
    }
    return Finding(**fields)  # type: ignore[arg-type]


class TestJsonRenderer:
    def test_round_trips_basic_fields(self) -> None:
        report = _report([_finding()])

        parsed = json.loads(json_renderer.render(report))

        assert parsed["scan_id"] == "scan123"
        assert parsed["engine"] == "web"
        assert parsed["target"] == "https://target.example"
        assert len(parsed["findings"]) == 1
        assert parsed["findings"][0]["severity"] == "low"

    def test_includes_risk_summary(self) -> None:
        report = _report([_finding(severity=Severity.CRITICAL)])

        parsed = json.loads(json_renderer.render(report))

        assert parsed["risk"]["max_severity"] == "critical"
        assert parsed["risk"]["score"] > 0

    def test_empty_findings_still_produces_valid_json(self) -> None:
        report = _report([])

        parsed = json.loads(json_renderer.render(report))

        assert parsed["findings"] == []
        assert parsed["risk"]["max_severity"] is None

    def test_json_default_converts_enum_to_its_value(self) -> None:
        assert json_renderer._json_default(Severity.HIGH) == "high"

    def test_json_default_stringifies_other_unknown_types(self) -> None:
        # Finding.metadata is dict[str, Any] - a plugin could stash anything
        # in it. The fallback must keep the whole report serializable
        # rather than raising TypeError mid-render for a type json.dumps
        # doesn't natively know.
        class Weird:
            def __str__(self) -> str:
                return "weird-repr"

        assert json_renderer._json_default(Weird()) == "weird-repr"


class TestCsvRenderer:
    def test_one_row_per_finding(self) -> None:
        report = _report([_finding(), _finding(title="Second finding")])

        rows = list(csv.DictReader(io.StringIO(csv_renderer.render(report))))

        assert len(rows) == 2
        assert rows[0]["title"] == "Missing X-Frame-Options header"
        assert rows[1]["title"] == "Second finding"

    def test_header_only_when_no_findings(self) -> None:
        report = _report([])

        rows = list(csv.DictReader(io.StringIO(csv_renderer.render(report))))

        assert rows == []


class TestMarkdownRenderer:
    def test_includes_executive_summary_fields(self) -> None:
        report = _report([_finding()])

        output = markdown_renderer.render(report)

        assert "# AutoFuzz Scan Report: test-profile" in output
        assert "scan123" in output
        assert "https://target.example" in output

    def test_no_findings_message(self) -> None:
        report = _report([])

        output = markdown_renderer.render(report)

        assert "No findings." in output

    def test_findings_sorted_most_severe_first(self) -> None:
        report = _report(
            [
                _finding(severity=Severity.LOW, title="low one"),
                _finding(severity=Severity.CRITICAL, title="critical one"),
            ]
        )

        output = markdown_renderer.render(report)

        assert output.index("critical one") < output.index("low one")

    def test_includes_stats_table(self) -> None:
        report = _report([])

        output = markdown_renderer.render(report)

        assert "pages_crawled" in output
        assert "| 5 |" in output


class TestHtmlRenderer:
    def test_renders_valid_html_shell(self) -> None:
        report = _report([_finding()])

        output = html_renderer.render(report)

        assert "<!doctype html>" in output.lower()
        assert "AutoFuzz Scan Report" in output
        assert "test-profile" in output

    def test_escapes_hostile_finding_content(self) -> None:
        # Finding data can come from the target under test - a hostile
        # target could try to plant a payload that executes when the
        # report is opened. Autoescaping must neutralize it.
        report = _report(
            [
                _finding(
                    description="<script>alert(1)</script>",
                    evidence="<img src=x onerror=alert(1)>",
                )
            ]
        )

        output = html_renderer.render(report)

        assert "<script>alert(1)</script>" not in output
        assert "&lt;script&gt;" in output

    def test_no_findings_message(self) -> None:
        report = _report([])

        output = html_renderer.render(report)

        assert "No findings." in output
