"""Report models and renderers (HTML, Markdown, JSON, CSV)."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from autofuzz.reporting.models import RiskScore, ScanReport
from autofuzz.reporting.renderers import csv as csv_renderer
from autofuzz.reporting.renderers import html as html_renderer
from autofuzz.reporting.renderers import json as json_renderer
from autofuzz.reporting.renderers import markdown as markdown_renderer

__all__ = ["ReportFormat", "RiskScore", "ScanReport", "default_extension", "render_report"]


class ReportFormat(str, Enum):
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"
    CSV = "csv"


_RENDERERS: dict[ReportFormat, Callable[[ScanReport], str]] = {
    ReportFormat.HTML: html_renderer.render,
    ReportFormat.MARKDOWN: markdown_renderer.render,
    ReportFormat.JSON: json_renderer.render,
    ReportFormat.CSV: csv_renderer.render,
}

_EXTENSIONS: dict[ReportFormat, str] = {
    ReportFormat.HTML: "html",
    ReportFormat.MARKDOWN: "md",
    ReportFormat.JSON: "json",
    ReportFormat.CSV: "csv",
}


def render_report(report: ScanReport, fmt: ReportFormat) -> str:
    return _RENDERERS[fmt](report)


def default_extension(fmt: ReportFormat) -> str:
    return _EXTENSIONS[fmt]
