"""Parameter discovery: extracts parameters from query strings and HTML forms."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from autofuzz.web.crawler import CrawlResult


@dataclass(frozen=True, slots=True)
class DiscoveredParam:
    name: str
    source: str  # "query" or "form"
    url: str
    method: str = "GET"


def _query_params(result: CrawlResult) -> list[DiscoveredParam]:
    query = urlparse(result.url).query
    if not query:
        return []
    return [
        DiscoveredParam(name=name, source="query", url=result.url)
        for name in sorted(parse_qs(query).keys())
    ]


def _form_params(result: CrawlResult) -> list[DiscoveredParam]:
    if not result.html:
        return []
    soup = BeautifulSoup(result.html, "html.parser")
    params: list[DiscoveredParam] = []
    for form in soup.find_all("form"):
        method = str(form.get("method", "GET")).upper()
        for field_el in form.find_all(["input", "textarea", "select"]):
            name = field_el.get("name")
            if name:
                params.append(
                    DiscoveredParam(name=str(name), source="form", url=result.url, method=method)
                )
    return params


def discover_params(crawl_results: list[CrawlResult]) -> list[DiscoveredParam]:
    """Extract deduplicated query-string and HTML-form parameters across a crawl."""
    seen: set[tuple[str, str, str, str]] = set()
    discovered: list[DiscoveredParam] = []
    for result in crawl_results:
        for param in [*_query_params(result), *_form_params(result)]:
            key = (param.name, param.source, param.url, param.method)
            if key not in seen:
                seen.add(key)
                discovered.append(param)
    return discovered
