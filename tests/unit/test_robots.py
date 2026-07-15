"""Unit tests for robots.txt parsing (Phase 4)."""

from __future__ import annotations

from autofuzz.web.discovery.robots import parse_robots_txt


def test_parses_disallow_allow_and_sitemap_directives() -> None:
    content = """
    User-agent: *
    Disallow: /admin
    Disallow: /private
    Allow: /public
    Sitemap: https://example.com/sitemap.xml
    """

    info = parse_robots_txt(content)

    assert info.found is True
    assert info.disallowed_paths == ["/admin", "/private"]
    assert info.allowed_paths == ["/public"]
    assert info.sitemap_urls == ["https://example.com/sitemap.xml"]


def test_ignores_comments_and_blank_lines() -> None:
    content = "# this is a comment\n\nUser-agent: *\nDisallow: /secret # trailing comment\n"

    info = parse_robots_txt(content)

    assert info.disallowed_paths == ["/secret"]


def test_empty_content_yields_no_directives() -> None:
    info = parse_robots_txt("")

    assert info.found is True
    assert info.disallowed_paths == []
    assert info.sitemap_urls == []


def test_directive_with_empty_value_is_ignored() -> None:
    info = parse_robots_txt("Disallow:\nAllow:   \n")

    assert info.disallowed_paths == []
    assert info.allowed_paths == []
