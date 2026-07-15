"""Unit tests for technology fingerprinting (Phase 4)."""

from __future__ import annotations

import httpx

from autofuzz.web.discovery.fingerprint import fingerprint_response


def _response(headers: dict[str, str], body: bytes = b"") -> httpx.Response:
    return httpx.Response(200, headers=headers, content=body)


def test_detects_server_header_technology() -> None:
    response = _response({"server": "nginx/1.25.0"})

    techs = fingerprint_response(response)

    assert any(t.name == "Nginx" and t.category == "web-server" for t in techs)


def test_detects_x_powered_by_header() -> None:
    response = _response({"x-powered-by": "Express"})

    techs = fingerprint_response(response)

    assert any(t.name == "Express" and t.category == "framework" for t in techs)


def test_detects_wordpress_from_body() -> None:
    response = _response(
        {"content-type": "text/html"},
        body=b"<html><head><link href='/wp-content/themes/x.css'></head></html>",
    )

    techs = fingerprint_response(response)

    assert any(t.name == "WordPress" and t.category == "cms" for t in techs)


def test_does_not_scan_body_for_non_html_content_type() -> None:
    response = _response(
        {"content-type": "application/json"},
        body=b'{"note": "wp-content mentioned but this is JSON"}',
    )

    techs = fingerprint_response(response)

    assert not any(t.name == "WordPress" for t in techs)


def test_deduplicates_repeated_signatures() -> None:
    response = _response(
        {"content-type": "text/html", "server": "nginx"},
        body=b"wp-content wp-content wp-content",
    )

    techs = fingerprint_response(response)
    names = [t.name for t in techs]

    assert names.count("WordPress") == 1


def test_no_signatures_yields_empty_list() -> None:
    response = _response({"content-type": "text/plain"}, body=b"nothing interesting here")

    assert fingerprint_response(response) == []
