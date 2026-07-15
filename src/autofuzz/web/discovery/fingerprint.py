"""Technology fingerprinting: lightweight, rule-based detection from response
headers and body content. No external fingerprint database dependency —
just a small set of well-known header and body signatures.

Operates on plain headers/body rather than an ``httpx.Response`` so it can
run against anything that looks like a fetched page - a live request or a
``CrawlResult`` collected earlier - without a dependency on httpx internals.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

_SERVER_HEADER_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"nginx", re.I), "Nginx", "web-server"),
    (re.compile(r"apache", re.I), "Apache HTTP Server", "web-server"),
    (re.compile(r"cloudflare", re.I), "Cloudflare", "cdn"),
    (re.compile(r"vsftpd", re.I), "vsftpd", "ftp-server"),
    (re.compile(r"iis", re.I), "Microsoft IIS", "web-server"),
    (re.compile(r"gunicorn", re.I), "Gunicorn", "app-server"),
)

_BODY_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"wp-content|wp-includes", re.I), "WordPress", "cms"),
    (re.compile(r"csrfmiddlewaretoken", re.I), "Django", "framework"),
    (re.compile(r"__viewstate", re.I), "ASP.NET WebForms", "framework"),
    (re.compile(r"laravel_session", re.I), "Laravel", "framework"),
)


@dataclass(frozen=True, slots=True)
class Technology:
    name: str
    category: str
    evidence: str


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def fingerprint(headers: Mapping[str, str], body: str = "") -> list[Technology]:
    """Rule-based technology detection from one response's headers and body."""
    found: list[Technology] = []

    server = _get_header(headers, "server") or ""
    for pattern, name, category in _SERVER_HEADER_RULES:
        if pattern.search(server):
            found.append(Technology(name=name, category=category, evidence=f"Server: {server}"))

    x_powered_by = _get_header(headers, "x-powered-by")
    if x_powered_by:
        found.append(
            Technology(
                name=x_powered_by,
                category="framework",
                evidence=f"X-Powered-By: {x_powered_by}",
            )
        )

    x_aspnet_version = _get_header(headers, "x-aspnet-version")
    if x_aspnet_version:
        found.append(
            Technology(
                name="ASP.NET",
                category="framework",
                evidence=f"X-AspNet-Version: {x_aspnet_version}",
            )
        )

    if _get_header(headers, "x-drupal-cache") is not None:
        found.append(
            Technology(name="Drupal", category="cms", evidence="X-Drupal-Cache header present")
        )

    content_type = _get_header(headers, "content-type") or ""
    if "text/html" in content_type and body:
        for pattern, name, category in _BODY_RULES:
            if pattern.search(body):
                found.append(
                    Technology(
                        name=name,
                        category=category,
                        evidence=f"body matched /{pattern.pattern}/",
                    )
                )

    seen: set[tuple[str, str]] = set()
    deduped: list[Technology] = []
    for tech in found:
        key = (tech.name, tech.category)
        if key not in seen:
            seen.add(key)
            deduped.append(tech)
    return deduped
