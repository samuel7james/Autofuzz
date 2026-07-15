"""robots.txt discovery: parses Disallow/Allow/Sitemap directives as discovery hints.

AutoFuzz's crawler does not enforce robots.txt exclusions on its own — for
an authorized security assessment, paths an operator tried to keep out of
search engines are frequently exactly what's worth enumerating. This module
only surfaces them as hints; ``WebEngineConfig.respect_robots_txt`` is left
for a later phase to wire into actual crawl behavior if desired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from autofuzz.web.http_client import HttpClient


@dataclass
class RobotsInfo:
    found: bool = False
    disallowed_paths: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    sitemap_urls: list[str] = field(default_factory=list)


def parse_robots_txt(content: str) -> RobotsInfo:
    """Parse robots.txt content into disallowed/allowed paths and sitemap URLs."""
    info = RobotsInfo(found=True)
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        directive, _, value = line.partition(":")
        directive = directive.strip().lower()
        value = value.strip()
        if not value:
            continue
        if directive == "disallow":
            info.disallowed_paths.append(value)
        elif directive == "allow":
            info.allowed_paths.append(value)
        elif directive == "sitemap":
            info.sitemap_urls.append(value)
    return info


async def discover_robots_txt(client: HttpClient, base_url: str) -> RobotsInfo:
    """Fetch and parse ``/robots.txt`` relative to ``base_url``."""
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        response = await client.get(robots_url)
    except Exception:
        return RobotsInfo(found=False)
    if response.status_code != 200:
        return RobotsInfo(found=False)
    return parse_robots_txt(response.text)
