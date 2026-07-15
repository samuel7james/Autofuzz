"""Unit tests for parameter discovery (Phase 4)."""

from __future__ import annotations

from autofuzz.web.crawler import CrawlResult
from autofuzz.web.discovery.params import discover_params


def test_discovers_query_string_params() -> None:
    results = [
        CrawlResult(url="https://example.com/search?q=test&page=2", status_code=200, depth=0)
    ]

    params = discover_params(results)
    names = {p.name for p in params}

    assert names == {"q", "page"}
    assert all(p.source == "query" for p in params)


def test_discovers_form_params() -> None:
    html = """
    <form method="post" action="/submit">
        <input name="email" type="email">
        <textarea name="message"></textarea>
        <select name="topic"></select>
        <input type="submit">
    </form>
    """
    results = [
        CrawlResult(
            url="https://example.com/contact",
            status_code=200,
            depth=0,
            content_type="text/html",
            html=html,
        )
    ]

    params = discover_params(results)
    by_name = {p.name: p for p in params}

    assert set(by_name) == {"email", "message", "topic"}
    assert all(p.source == "form" and p.method == "POST" for p in by_name.values())


def test_deduplicates_params_across_results() -> None:
    results = [
        CrawlResult(url="https://example.com/a?ref=x", status_code=200, depth=0),
        CrawlResult(url="https://example.com/b?ref=y", status_code=200, depth=0),
    ]

    params = discover_params(results)

    # Same param name but different URLs are distinct discoveries (url is part of the key).
    assert len(params) == 2


def test_page_with_no_params_yields_nothing() -> None:
    results = [CrawlResult(url="https://example.com/static", status_code=200, depth=0)]

    assert discover_params(results) == []
