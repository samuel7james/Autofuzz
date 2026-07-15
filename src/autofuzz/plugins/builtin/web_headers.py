"""Built-in web plugins: passive HTTP header and cookie analysis.

Every plugin here only reads data the crawler already collected on a
``CrawlResult`` (status, headers, body) - none of them make their own
requests. Non-intrusive, configurable, suitable for authorized assessment
per PROJECT_PLAN.md's Assessment Framework scope (passive analysis,
metadata inspection - no active exploitation).
"""

from __future__ import annotations

import re
from typing import Any

from autofuzz.plugins.base import Finding, Plugin, PluginMetadata, Severity
from autofuzz.web.crawler import CrawlResult

_RECOMMENDED_SECURITY_HEADERS: dict[str, Severity] = {
    "strict-transport-security": Severity.LOW,
    "x-content-type-options": Severity.LOW,
    "x-frame-options": Severity.LOW,
    "content-security-policy": Severity.MEDIUM,
}

_VERSION_PATTERN = re.compile(r"\d+\.\d+(\.\d+)?")


class MissingSecurityHeadersPlugin(Plugin[CrawlResult]):
    """Flags well-known security headers that are absent from a response."""

    metadata = PluginMetadata(
        id="web.missing-security-headers",
        name="Missing Security Headers",
        description="Flags absent Strict-Transport-Security, X-Content-Type-Options, "
        "X-Frame-Options, and Content-Security-Policy headers.",
        engine="web",
    )

    def __init__(self) -> None:
        self._headers_to_check = dict(_RECOMMENDED_SECURITY_HEADERS)

    def configure(self, options: dict[str, Any]) -> None:
        ignore = options.get("ignore_headers", [])
        for header in ignore:
            self._headers_to_check.pop(str(header).lower(), None)

    def applies_to(self, context: CrawlResult) -> bool:
        return context.status_code is not None

    def run(self, context: CrawlResult) -> list[Finding]:
        present = {key.lower() for key in context.headers}
        findings: list[Finding] = []
        for header, severity in self._headers_to_check.items():
            if header not in present:
                findings.append(
                    Finding(
                        plugin_id=self.metadata.id,
                        title=f"Missing {header} header",
                        severity=severity,
                        description=f"The response did not set a '{header}' header.",
                        target=context.url,
                        evidence=f"Response headers: {sorted(present)}",
                    )
                )
        return findings


class InsecureCookiePlugin(Plugin[CrawlResult]):
    """Flags Set-Cookie headers missing Secure, HttpOnly, or SameSite attributes."""

    metadata = PluginMetadata(
        id="web.insecure-cookies",
        name="Insecure Cookie Attributes",
        description="Flags cookies set without Secure, HttpOnly, or SameSite attributes.",
        engine="web",
    )

    def applies_to(self, context: CrawlResult) -> bool:
        return "set-cookie" in {key.lower() for key in context.headers}

    def run(self, context: CrawlResult) -> list[Finding]:
        cookie_header = next(
            (value for key, value in context.headers.items() if key.lower() == "set-cookie"), ""
        )
        lowered = cookie_header.lower()
        required_attrs = (("Secure", "secure"), ("HttpOnly", "httponly"), ("SameSite", "samesite"))
        missing = [attr for attr, token in required_attrs if token not in lowered]
        if not missing:
            return []
        return [
            Finding(
                plugin_id=self.metadata.id,
                title="Cookie set without recommended attributes",
                severity=Severity.MEDIUM,
                description=f"Set-Cookie header is missing: {', '.join(missing)}.",
                target=context.url,
                evidence=cookie_header,
            )
        ]


class ServerDisclosurePlugin(Plugin[CrawlResult]):
    """Flags Server/X-Powered-By headers that disclose a specific version number."""

    metadata = PluginMetadata(
        id="web.server-version-disclosure",
        name="Server Version Disclosure",
        description="Flags Server/X-Powered-By headers that include a specific version number.",
        engine="web",
    )

    def applies_to(self, context: CrawlResult) -> bool:
        headers = {key.lower() for key in context.headers}
        return "server" in headers or "x-powered-by" in headers

    def run(self, context: CrawlResult) -> list[Finding]:
        findings: list[Finding] = []
        for key, value in context.headers.items():
            if key.lower() not in ("server", "x-powered-by"):
                continue
            if _VERSION_PATTERN.search(value):
                findings.append(
                    Finding(
                        plugin_id=self.metadata.id,
                        title=f"{key} header discloses a version number",
                        severity=Severity.INFO,
                        description=f"The '{key}' header reveals specific software version info.",
                        target=context.url,
                        evidence=f"{key}: {value}",
                    )
                )
        return findings
