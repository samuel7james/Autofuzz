"""JSON report renderer."""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum

from autofuzz.reporting.models import ScanReport


def _json_default(obj: object) -> object:
    if isinstance(obj, Enum):
        return obj.value
    return str(obj)


def render(report: ScanReport) -> str:
    data = asdict(report)
    data["risk"] = asdict(report.risk)
    return json.dumps(data, indent=2, default=_json_default)
