"""HTML report renderer (Jinja2 template).

Autoescaping is mandatory, not optional: a Finding's evidence/description
can contain text sourced directly from the target under test, which - for
a security assessment tool - is inherently untrusted input. Without
escaping, a hostile target could plant a payload that executes when the
generated report is later opened in a browser.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from autofuzz.plugins.base import Severity
from autofuzz.reporting.models import ScanReport

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]

# Semgrep's direct-use-of-jinja2 rule assumes a Flask app and suggests
# render_template() instead - not applicable here (no Flask, no request
# context). What it's actually checking for is autoescaping, which IS
# explicitly enabled below (not left to filename-based autodetection,
# which would silently be False for a `.jinja`-suffixed template name).
# Covered by a dedicated XSS-escaping test in tests/unit/test_report_renderers.py.
_env = Environment(  # nosemgrep
    loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True
)


def render(report: ScanReport) -> str:
    template = _env.get_template("report.html.jinja")
    severity_counts = [
        (severity.value, report.risk.counts_by_severity.get(severity, 0))
        for severity in _SEVERITY_ORDER
    ]
    sorted_findings = sorted(
        report.findings, key=lambda finding: _SEVERITY_ORDER.index(finding.severity)
    )
    # nosemgrep: python.flask.security.xss.audit.direct-use-of-jinja2.direct-use-of-jinja2
    return template.render(
        report=report, severity_counts=severity_counts, sorted_findings=sorted_findings
    )
