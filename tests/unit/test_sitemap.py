"""Unit tests for sitemap.xml parsing (Phase 4)."""

from __future__ import annotations

from autofuzz.web.discovery.sitemap import parse_sitemap_xml


def test_parses_urlset() -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/</loc></url>
        <url><loc>https://example.com/about</loc></url>
    </urlset>"""

    info = parse_sitemap_xml(content)

    assert info.found is True
    assert info.urls == ["https://example.com/", "https://example.com/about"]
    assert info.nested_sitemaps == []


def test_parses_sitemap_index() -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://example.com/sitemap-1.xml</loc></sitemap>
        <sitemap><loc>https://example.com/sitemap-2.xml</loc></sitemap>
    </sitemapindex>"""

    info = parse_sitemap_xml(content)

    assert info.found is True
    assert info.urls == []
    assert info.nested_sitemaps == [
        "https://example.com/sitemap-1.xml",
        "https://example.com/sitemap-2.xml",
    ]


def test_malformed_xml_returns_not_found() -> None:
    info = parse_sitemap_xml("<urlset><url><loc>unterminated")

    assert info.found is False
    assert info.urls == []


def test_entity_expansion_payload_does_not_crash_parser() -> None:
    # A billion-laughs-style payload should be rejected/blocked by defusedxml,
    # not expanded or allowed to hang the parser.
    payload = """<?xml version="1.0"?>
    <!DOCTYPE urlset [
      <!ENTITY a "spam">
      <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
    ]>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>&b;</loc></url>
    </urlset>"""

    info = parse_sitemap_xml(payload)

    assert info.found is False
