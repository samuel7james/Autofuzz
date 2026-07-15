"""Web Assessment Engine: orchestrates a crawl, runs assessment plugins and
technology fingerprinting against every fetched page, and returns the
resulting Findings plus scan statistics.

This is what finally makes `autofuzz web <url>` a real, runnable scan
instead of a stub - it reuses the Phase 4 crawler/discovery modules and the
Phase 5 plugin registry/built-in plugins unchanged.
"""

from __future__ import annotations

from autofuzz.core.config import SchedulerConfig, WebEngineConfig
from autofuzz.core.logging import get_logger
from autofuzz.core.plugin import PluginRegistry
from autofuzz.plugins.base import Finding, Severity
from autofuzz.plugins.builtin.web_headers import (
    InsecureCookiePlugin,
    MissingSecurityHeadersPlugin,
    ServerDisclosurePlugin,
)
from autofuzz.web.crawler import Crawler, CrawlResult
from autofuzz.web.discovery.endpoints import enumerate_endpoints
from autofuzz.web.discovery.fingerprint import fingerprint
from autofuzz.web.discovery.params import discover_params

log = get_logger(__name__)


def default_web_plugin_registry() -> PluginRegistry[CrawlResult]:
    """The built-in passive web plugins, registered and ready to run."""
    registry: PluginRegistry[CrawlResult] = PluginRegistry()
    registry.register(MissingSecurityHeadersPlugin())
    registry.register(InsecureCookiePlugin())
    registry.register(ServerDisclosurePlugin())
    return registry


class WebAssessmentEngine:
    """Crawls a target and runs the plugin registry against every fetched page."""

    def __init__(
        self,
        web_config: WebEngineConfig,
        scheduler_config: SchedulerConfig,
        registry: PluginRegistry[CrawlResult] | None = None,
    ) -> None:
        self._web_config = web_config
        self._scheduler_config = scheduler_config
        self._registry = registry or default_web_plugin_registry()

    async def run(self, start_url: str) -> tuple[list[Finding], dict[str, int]]:
        crawler = Crawler(self._web_config, self._scheduler_config)
        results = await crawler.crawl(start_url)

        findings: list[Finding] = []
        for result in results:
            findings.extend(self._registry.run_all(result))
            findings.extend(self._fingerprint_findings(result))

        stats = {
            "pages_crawled": len(results),
            "endpoints_found": len(enumerate_endpoints(results)),
            "params_found": len(discover_params(results)),
            "findings_found": len(findings),
        }
        return findings, stats

    def _fingerprint_findings(self, result: CrawlResult) -> list[Finding]:
        if result.status_code is None:
            return []
        technologies = fingerprint(result.headers, result.html or "")
        return [
            Finding(
                plugin_id="web.technology-fingerprint",
                title=f"Detected technology: {tech.name}",
                severity=Severity.INFO,
                description=f"Identified {tech.name} ({tech.category}) via {tech.evidence}.",
                target=result.url,
                evidence=tech.evidence,
                metadata={"technology": tech.name, "category": tech.category},
            )
            for tech in technologies
        ]
