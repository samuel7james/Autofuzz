"""Unit tests for technology fingerprinting (Phase 4/6)."""

from __future__ import annotations

from autofuzz.web.discovery.fingerprint import fingerprint


def test_detects_server_header_technology() -> None:
    techs = fingerprint({"server": "nginx/1.25.0"})

    assert any(t.name == "Nginx" and t.category == "web-server" for t in techs)


def test_detects_x_powered_by_header() -> None:
    techs = fingerprint({"x-powered-by": "Express"})

    assert any(t.name == "Express" and t.category == "framework" for t in techs)


def test_header_lookup_is_case_insensitive() -> None:
    techs = fingerprint({"Server": "nginx"})

    assert any(t.name == "Nginx" for t in techs)


def test_detects_wordpress_from_body() -> None:
    techs = fingerprint(
        {"content-type": "text/html"},
        body="<html><head><link href='/wp-content/themes/x.css'></head></html>",
    )

    assert any(t.name == "WordPress" and t.category == "cms" for t in techs)


def test_does_not_scan_body_for_non_html_content_type() -> None:
    techs = fingerprint(
        {"content-type": "application/json"},
        body='{"note": "wp-content mentioned but this is JSON"}',
    )

    assert not any(t.name == "WordPress" for t in techs)


def test_deduplicates_repeated_signatures() -> None:
    techs = fingerprint(
        {"content-type": "text/html", "server": "nginx"},
        body="wp-content wp-content wp-content",
    )
    names = [t.name for t in techs]

    assert names.count("WordPress") == 1


def test_no_signatures_yields_empty_list() -> None:
    assert fingerprint({"content-type": "text/plain"}, body="nothing interesting here") == []


def test_empty_headers_and_body_yields_empty_list() -> None:
    assert fingerprint({}) == []
