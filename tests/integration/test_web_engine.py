"""Integration tests: crawler + discovery modules against a real local static
HTTP server (not mocked), exercising the full Phase 4 web engine pipeline.
"""

from __future__ import annotations

from autofuzz.core.config import SchedulerConfig, WebEngineConfig
from autofuzz.web.crawler import Crawler
from autofuzz.web.discovery.endpoints import enumerate_endpoints
from autofuzz.web.discovery.fingerprint import fingerprint
from autofuzz.web.discovery.graph import RequestGraph
from autofuzz.web.discovery.params import discover_params
from autofuzz.web.discovery.robots import discover_robots_txt
from autofuzz.web.discovery.sitemap import discover_sitemap
from autofuzz.web.http_client import HttpClient


def _configs() -> tuple[WebEngineConfig, SchedulerConfig]:
    return (
        WebEngineConfig(max_crawl_depth=3, max_pages=50),
        SchedulerConfig(concurrency=5, rate_limit_per_second=1000, max_retries=0),
    )


async def test_crawler_stays_in_scope_and_follows_links(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    crawler = Crawler(web_config, scheduler_config)

    results = await crawler.crawl(f"{static_site}/index.html")

    urls = {r.url for r in results}
    assert f"{static_site}/index.html" in urls
    assert f"{static_site}/about.html" in urls
    assert f"{static_site}/contact.html?ref=home" in urls
    assert not any("external.example" in u for u in urls)


async def test_crawler_reports_progress_per_page(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    progress_calls: list[tuple[int, int]] = []

    def on_progress(pages_fetched: int, max_pages: int) -> None:
        progress_calls.append((pages_fetched, max_pages))

    crawler = Crawler(web_config, scheduler_config, on_progress)
    results = await crawler.crawl(f"{static_site}/index.html")

    # One callback per fetched page, not per depth level - a level with
    # many URLs must not go silent until the whole level finishes.
    assert len(progress_calls) == len(results)
    assert progress_calls[-1] == (len(results), web_config.max_pages)
    # Pages-fetched increases by exactly 1 each call, in order.
    assert [c[0] for c in progress_calls] == list(range(1, len(results) + 1))


async def test_crawler_respects_max_pages(static_site: str) -> None:
    web_config = WebEngineConfig(max_crawl_depth=3, max_pages=1)
    scheduler_config = SchedulerConfig(concurrency=5, rate_limit_per_second=1000, max_retries=0)
    crawler = Crawler(web_config, scheduler_config)

    results = await crawler.crawl(f"{static_site}/index.html")

    assert len(results) == 1


async def test_endpoint_enumeration_from_real_crawl(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    crawler = Crawler(web_config, scheduler_config)
    results = await crawler.crawl(f"{static_site}/index.html")

    endpoints = enumerate_endpoints(results)

    assert all(e.status_code == 200 for e in endpoints)
    assert any(e.has_query_params for e in endpoints)


async def test_param_discovery_from_real_crawl(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    crawler = Crawler(web_config, scheduler_config)
    results = await crawler.crawl(f"{static_site}/index.html")

    names = {p.name for p in discover_params(results)}

    assert "ref" in names
    assert "email" in names
    assert "message" in names


async def test_request_graph_tracks_discovery_edges(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    crawler = Crawler(web_config, scheduler_config)
    results = await crawler.crawl(f"{static_site}/index.html")

    graph = RequestGraph.from_crawl_results(results)

    assert f"{static_site}/index.html" in graph.discovered_via(f"{static_site}/about.html")


async def test_robots_txt_discovery(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    async with HttpClient(web_config, scheduler_config) as client:
        info = await discover_robots_txt(client, static_site + "/")

    assert info.found is True
    assert "/admin" in info.disallowed_paths
    assert info.sitemap_urls


async def test_sitemap_discovery(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    async with HttpClient(web_config, scheduler_config) as client:
        info = await discover_sitemap(client, static_site + "/")

    assert info.found is True
    assert any("index.html" in u for u in info.urls)


async def test_fingerprint_runs_cleanly_against_a_real_response(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    async with HttpClient(web_config, scheduler_config) as client:
        response = await client.get(f"{static_site}/index.html")

    # http.server's default Server header identifies itself as a
    # BaseHTTP-derived Python server; no bundled rule matches that
    # specifically, so this just confirms fingerprinting runs cleanly
    # against a real response without raising.
    techs = fingerprint(dict(response.headers), response.text)
    assert isinstance(techs, list)
