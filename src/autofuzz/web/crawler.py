"""Link-following web crawler with scope and depth limits.

Breadth-first: fetches one full depth level through the shared
``WorkerPool`` (bounded concurrency, rate limiting, retries), extracts
links from HTML, then only advances into the next level with links that
are same-origin and not yet visited. Bounded by ``max_crawl_depth`` and
``max_pages`` from ``WebEngineConfig``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from autofuzz.core.config import SchedulerConfig, WebEngineConfig
from autofuzz.core.logging import get_logger
from autofuzz.core.scheduler import WorkerPool
from autofuzz.web.http_client import HttpClient

log = get_logger(__name__)

_LINK_ATTRS: tuple[tuple[str, str], ...] = (
    ("a", "href"),
    ("link", "href"),
    ("script", "src"),
    ("img", "src"),
)


@dataclass
class CrawlResult:
    """One fetched page: its URL, status, headers, links found on it, and (for HTML) its body."""

    url: str
    status_code: int | None
    depth: int
    discovered_links: list[str] = field(default_factory=list)
    content_type: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    html: str | None = None
    error: str | None = None


def _same_scope(url: str, origin: str) -> bool:
    return urlparse(url).netloc == urlparse(origin).netloc


def _extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for tag, attr in _LINK_ATTRS:
        for element in soup.find_all(tag):
            value = element.get(attr)
            if not value:
                continue
            absolute = urljoin(base_url, str(value))
            if absolute.startswith(("http://", "https://")):
                links.append(absolute.split("#", 1)[0])
    return links


CrawlProgressCallback = Callable[[int, int], None]
"""Called as each page is fetched with (pages_fetched, max_pages)."""


class Crawler:
    """Breadth-first crawl of a single origin, bounded by depth and page count."""

    def __init__(
        self,
        web_config: WebEngineConfig,
        scheduler_config: SchedulerConfig,
        on_progress: CrawlProgressCallback | None = None,
    ) -> None:
        self._web_config = web_config
        self._scheduler_config = scheduler_config
        self._on_progress = on_progress

    async def crawl(self, start_url: str) -> list[CrawlResult]:
        origin = start_url
        visited: set[str] = {start_url}
        results: list[CrawlResult] = []
        current_level: list[str] = [start_url]
        depth = 0
        pages_fetched = 0

        def notify_page_fetched() -> None:
            nonlocal pages_fetched
            pages_fetched += 1
            if self._on_progress:
                self._on_progress(pages_fetched, self._web_config.max_pages)

        async with HttpClient(self._web_config, self._scheduler_config) as client:
            while (
                current_level
                and depth <= self._web_config.max_crawl_depth
                and len(results) < self._web_config.max_pages
            ):
                pool: WorkerPool[CrawlResult] = WorkerPool(self._scheduler_config)
                jobs = [self._fetch_job(client, url, depth) for url in current_level]
                # Per-page progress, not per-level: a single level can hold
                # hundreds of URLs, and reporting only once the whole level
                # finishes made a long level look frozen the entire time.
                batch_results = await pool.run_all(jobs, on_job_done=notify_page_fetched)

                next_level: list[str] = []
                for result in batch_results:
                    if isinstance(result, BaseException):
                        log.warning("crawl_fetch_failed", error=str(result))
                        continue
                    results.append(result)
                    if len(results) >= self._web_config.max_pages:
                        break
                    for link in result.discovered_links:
                        if link not in visited and _same_scope(link, origin):
                            visited.add(link)
                            next_level.append(link)

                current_level = next_level
                depth += 1

        return results[: self._web_config.max_pages]

    def _fetch_job(
        self, client: HttpClient, url: str, depth: int
    ) -> Callable[[], Awaitable[CrawlResult]]:
        async def job() -> CrawlResult:
            try:
                response = await client.get(url)
            except Exception as exc:
                return CrawlResult(url=url, status_code=None, depth=depth, error=str(exc))

            content_type = response.headers.get("content-type", "")
            links: list[str] = []
            html: str | None = None
            if "text/html" in content_type:
                html = response.text
                links = _extract_links(url, html)
            return CrawlResult(
                url=url,
                status_code=response.status_code,
                depth=depth,
                discovered_links=links,
                content_type=content_type,
                headers=dict(response.headers),
                html=html,
            )

        return job
