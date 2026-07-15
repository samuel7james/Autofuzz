"""Technology fingerprinting: lightweight, rule-based detection from response
headers and body content. No external fingerprint database dependency —
just a small set of well-known header and body signatures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

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


def fingerprint_response(response: httpx.Response) -> list[Technology]:
    """Rule-based technology detection from one HTTP response's headers and body."""
    found: list[Technology] = []

    server = response.headers.get("server", "")
    for pattern, name, category in _SERVER_HEADER_RULES:
        if pattern.search(server):
            found.append(Technology(name=name, category=category, evidence=f"Server: {server}"))

    x_powered_by = response.headers.get("x-powered-by")
    if x_powered_by:
        found.append(
            Technology(
                name=x_powered_by,
                category="framework",
                evidence=f"X-Powered-By: {x_powered_by}",
            )
        )

    if "x-aspnet-version" in response.headers:
        found.append(
            Technology(
                name="ASP.NET",
                category="framework",
                evidence=f"X-AspNet-Version: {response.headers['x-aspnet-version']}",
            )
        )

    if "x-drupal-cache" in response.headers:
        found.append(
            Technology(name="Drupal", category="cms", evidence="X-Drupal-Cache header present")
        )

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        body = response.text
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
