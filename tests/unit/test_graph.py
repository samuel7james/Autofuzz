"""Unit tests for the request graph model (Phase 4)."""

from __future__ import annotations

from autofuzz.web.crawler import CrawlResult
from autofuzz.web.discovery.graph import RequestGraph


def test_from_crawl_results_builds_nodes_and_edges() -> None:
    results = [
        CrawlResult(
            url="https://example.com/",
            status_code=200,
            depth=0,
            discovered_links=["https://example.com/about", "https://example.com/contact"],
        ),
        CrawlResult(url="https://example.com/about", status_code=200, depth=1),
    ]

    graph = RequestGraph.from_crawl_results(results)

    assert "https://example.com/" in graph.nodes
    assert "https://example.com/about" in graph.nodes
    assert "https://example.com/contact" in graph.nodes
    assert len(graph.edges) == 2


def test_discovered_via_returns_source_urls() -> None:
    results = [
        CrawlResult(
            url="https://example.com/",
            status_code=200,
            depth=0,
            discovered_links=["https://example.com/about"],
        ),
        CrawlResult(
            url="https://example.com/nav",
            status_code=200,
            depth=0,
            discovered_links=["https://example.com/about"],
        ),
    ]

    graph = RequestGraph.from_crawl_results(results)

    assert set(graph.discovered_via("https://example.com/about")) == {
        "https://example.com/",
        "https://example.com/nav",
    }


def test_discovered_via_empty_for_unknown_url() -> None:
    graph = RequestGraph()

    assert graph.discovered_via("https://example.com/nowhere") == []
