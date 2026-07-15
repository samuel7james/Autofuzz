"""sitemap.xml discovery: parses standard sitemaps and sitemap indexes.

Uses ``defusedxml`` instead of the stdlib XML parser because sitemap
content comes from the target under test — for an authorized assessment
that's still untrusted input, and XML entity-expansion attacks are a real
risk when parsing arbitrary target-supplied XML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from defusedxml import ElementTree as SafeElementTree

from autofuzz.core.logging import get_logger
from autofuzz.web.http_client import HttpClient

log = get_logger(__name__)

_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class SitemapInfo:
    found: bool = False
    urls: list[str] = field(default_factory=list)
    nested_sitemaps: list[str] = field(default_factory=list)


def parse_sitemap_xml(content: str) -> SitemapInfo:
    """Parse a ``<urlset>`` or ``<sitemapindex>`` document into discovered URLs."""
    try:
        root = SafeElementTree.fromstring(content)
    except Exception as exc:
        log.warning("sitemap_parse_failed", error=str(exc))
        return SitemapInfo(found=False)

    info = SitemapInfo(found=True)
    if root.tag.endswith("sitemapindex"):
        for sitemap_el in root.findall(f"{_SITEMAP_NS}sitemap"):
            loc = sitemap_el.findtext(f"{_SITEMAP_NS}loc")
            if loc:
                info.nested_sitemaps.append(loc.strip())
    elif root.tag.endswith("urlset"):
        for url_el in root.findall(f"{_SITEMAP_NS}url"):
            loc = url_el.findtext(f"{_SITEMAP_NS}loc")
            if loc:
                info.urls.append(loc.strip())
    return info


async def discover_sitemap(
    client: HttpClient, base_url: str, path: str = "/sitemap.xml"
) -> SitemapInfo:
    """Fetch and parse a sitemap at ``path`` relative to ``base_url``."""
    sitemap_url = urljoin(base_url, path)
    try:
        response = await client.get(sitemap_url)
    except Exception:
        return SitemapInfo(found=False)
    if response.status_code != 200:
        return SitemapInfo(found=False)
    return parse_sitemap_xml(response.text)
