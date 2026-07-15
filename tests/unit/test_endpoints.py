"""Unit tests for endpoint enumeration (Phase 4)."""

from __future__ import annotations

from autofuzz.web.crawler import CrawlResult
from autofuzz.web.discovery.endpoints import enumerate_endpoints


def test_deduplicates_and_sorts_endpoints() -> None:
    results = [
        CrawlResult(url="https://example.com/b", status_code=200, depth=0),
        CrawlResult(url="https://example.com/a", status_code=200, depth=0),
        CrawlResult(url="https://example.com/a", status_code=200, depth=1),  # duplicate URL
    ]

    endpoints = enumerate_endpoints(results)

    assert [e.url for e in endpoints] == ["https://example.com/a", "https://example.com/b"]


def test_skips_failed_fetches() -> None:
    results = [
        CrawlResult(url="https://example.com/ok", status_code=200, depth=0),
        CrawlResult(url="https://example.com/fail", status_code=None, depth=0, error="timeout"),
    ]

    endpoints = enumerate_endpoints(results)

    assert len(endpoints) == 1
    assert endpoints[0].url == "https://example.com/ok"


def test_flags_query_params() -> None:
    results = [
        CrawlResult(url="https://example.com/search?q=test", status_code=200, depth=0),
        CrawlResult(url="https://example.com/static", status_code=200, depth=0),
    ]

    endpoints = enumerate_endpoints(results)
    by_url = {e.url: e for e in endpoints}

    assert by_url["https://example.com/search?q=test"].has_query_params is True
    assert by_url["https://example.com/static"].has_query_params is False
