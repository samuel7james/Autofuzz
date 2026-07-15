"""Endpoint enumeration: turns raw crawl results into a deduplicated,
sorted list of endpoints worth further assessment.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from autofuzz.web.crawler import CrawlResult


@dataclass(frozen=True, slots=True)
class Endpoint:
    url: str
    method: str
    status_code: int
    content_type: str | None
    has_query_params: bool


def enumerate_endpoints(crawl_results: list[CrawlResult]) -> list[Endpoint]:
    """Deduplicate successfully fetched crawl results into a sorted endpoint list."""
    seen: dict[str, Endpoint] = {}
    for result in crawl_results:
        if result.status_code is None:
            continue
        seen[result.url] = Endpoint(
            url=result.url,
            method="GET",
            status_code=result.status_code,
            content_type=result.content_type,
            has_query_params=bool(urlparse(result.url).query),
        )
    return sorted(seen.values(), key=lambda endpoint: endpoint.url)
