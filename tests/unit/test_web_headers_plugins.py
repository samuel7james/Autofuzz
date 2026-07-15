"""Unit tests for the built-in passive web header plugins (Phase 5)."""

from __future__ import annotations

from autofuzz.plugins.builtin.web_headers import (
    InsecureCookiePlugin,
    MissingSecurityHeadersPlugin,
    ServerDisclosurePlugin,
)
from autofuzz.web.crawler import CrawlResult


def _result(headers: dict[str, str], status_code: int | None = 200) -> CrawlResult:
    return CrawlResult(
        url="https://example.com/", status_code=status_code, depth=0, headers=headers
    )


class TestMissingSecurityHeadersPlugin:
    def test_applies_to_fetched_pages_only(self) -> None:
        plugin = MissingSecurityHeadersPlugin()

        assert plugin.applies_to(_result({}, status_code=200)) is True
        assert plugin.applies_to(_result({}, status_code=None)) is False

    def test_flags_all_missing_headers(self) -> None:
        plugin = MissingSecurityHeadersPlugin()

        findings = plugin.run(_result({}))

        titles = {f.title for f in findings}
        assert "Missing strict-transport-security header" in titles
        assert "Missing content-security-policy header" in titles
        assert len(findings) == 4

    def test_no_findings_when_all_headers_present(self) -> None:
        plugin = MissingSecurityHeadersPlugin()
        headers = {
            "Strict-Transport-Security": "max-age=31536000",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'",
        }

        assert plugin.run(_result(headers)) == []

    def test_configure_ignores_specified_headers(self) -> None:
        plugin = MissingSecurityHeadersPlugin()
        plugin.configure({"ignore_headers": ["x-frame-options", "content-security-policy"]})

        findings = plugin.run(_result({}))

        titles = {f.title for f in findings}
        assert "Missing x-frame-options header" not in titles
        assert len(findings) == 2


class TestInsecureCookiePlugin:
    def test_does_not_apply_without_set_cookie(self) -> None:
        plugin = InsecureCookiePlugin()

        assert plugin.applies_to(_result({})) is False

    def test_flags_cookie_missing_all_attributes(self) -> None:
        plugin = InsecureCookiePlugin()

        findings = plugin.run(_result({"Set-Cookie": "session=abc123"}))

        assert len(findings) == 1
        assert "Secure" in findings[0].description
        assert "HttpOnly" in findings[0].description
        assert "SameSite" in findings[0].description

    def test_no_findings_for_fully_attributed_cookie(self) -> None:
        plugin = InsecureCookiePlugin()
        cookie = "session=abc123; Secure; HttpOnly; SameSite=Strict"

        assert plugin.run(_result({"Set-Cookie": cookie})) == []

    def test_flags_partial_attributes(self) -> None:
        plugin = InsecureCookiePlugin()

        findings = plugin.run(_result({"Set-Cookie": "session=abc123; Secure"}))

        assert len(findings) == 1
        assert "HttpOnly" in findings[0].description
        assert "Secure" not in findings[0].description


class TestServerDisclosurePlugin:
    def test_does_not_apply_without_relevant_headers(self) -> None:
        plugin = ServerDisclosurePlugin()

        assert plugin.applies_to(_result({})) is False

    def test_flags_server_header_with_version(self) -> None:
        plugin = ServerDisclosurePlugin()

        findings = plugin.run(_result({"Server": "nginx/1.25.3"}))

        assert len(findings) == 1
        assert "Server" in findings[0].title

    def test_does_not_flag_generic_server_header(self) -> None:
        plugin = ServerDisclosurePlugin()

        findings = plugin.run(_result({"Server": "nginx"}))

        assert findings == []

    def test_flags_x_powered_by_with_version(self) -> None:
        plugin = ServerDisclosurePlugin()

        findings = plugin.run(_result({"X-Powered-By": "PHP/8.2.1"}))

        assert len(findings) == 1
