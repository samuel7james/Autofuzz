"""Unit tests for crawler helper functions (Phase 4). Full BFS crawl behavior
is covered by tests/integration/test_web_engine.py against a real server.
"""

from __future__ import annotations

from autofuzz.web.crawler import _extract_links, _same_scope


def test_extract_links_resolves_relative_urls() -> None:
    html = '<a href="/about">About</a><a href="contact.html">Contact</a>'

    links = _extract_links("https://example.com/dir/index.html", html)

    assert "https://example.com/about" in links
    assert "https://example.com/dir/contact.html" in links


def test_extract_links_strips_fragments() -> None:
    html = '<a href="/page#section-2">Jump</a>'

    links = _extract_links("https://example.com/", html)

    assert links == ["https://example.com/page"]


def test_extract_links_ignores_non_http_schemes() -> None:
    html = '<a href="mailto:test@example.com">Mail</a><a href="javascript:void(0)">JS</a>'

    links = _extract_links("https://example.com/", html)

    assert links == []


def test_extract_links_covers_script_and_img_src() -> None:
    html = '<script src="/app.js"></script><img src="/logo.png">'

    links = _extract_links("https://example.com/", html)

    assert "https://example.com/app.js" in links
    assert "https://example.com/logo.png" in links


def test_same_scope_matches_identical_netloc() -> None:
    assert _same_scope("https://example.com/a", "https://example.com/b") is True


def test_same_scope_rejects_different_host() -> None:
    assert _same_scope("https://other.com/a", "https://example.com/b") is False


def test_same_scope_rejects_different_port() -> None:
    assert _same_scope("https://example.com:8080/a", "https://example.com/b") is False
