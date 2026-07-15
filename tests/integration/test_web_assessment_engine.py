"""Integration tests: WebAssessmentEngine (crawl + plugins + fingerprint)
against a real local static HTTP server (not mocked) (Phase 6).
"""

from __future__ import annotations

from autofuzz.core.config import SchedulerConfig, WebEngineConfig
from autofuzz.web.engine import WebAssessmentEngine


def _configs() -> tuple[WebEngineConfig, SchedulerConfig]:
    return (
        WebEngineConfig(max_crawl_depth=3, max_pages=50),
        SchedulerConfig(concurrency=5, rate_limit_per_second=1000, max_retries=0),
    )


async def test_engine_run_produces_missing_header_findings(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    engine = WebAssessmentEngine(web_config, scheduler_config)

    findings, stats = await engine.run(f"{static_site}/index.html")

    # The fixture site serves plain http.server responses with none of the
    # recommended security headers set, so every crawled page should trip
    # MissingSecurityHeadersPlugin.
    assert any(f.plugin_id == "web.missing-security-headers" for f in findings)
    assert stats["pages_crawled"] >= 3
    assert stats["findings_found"] == len(findings)


async def test_engine_run_stats_match_discovery_modules(static_site: str) -> None:
    web_config, scheduler_config = _configs()
    engine = WebAssessmentEngine(web_config, scheduler_config)

    _findings, stats = await engine.run(f"{static_site}/index.html")

    assert stats["endpoints_found"] >= 1
    assert stats["params_found"] >= 1  # the contact form + query-string param


async def test_engine_respects_plugin_registry_configuration(static_site: str) -> None:
    from autofuzz.core.plugin import PluginRegistry
    from autofuzz.plugins.builtin.web_headers import MissingSecurityHeadersPlugin
    from autofuzz.web.crawler import CrawlResult

    registry: PluginRegistry[CrawlResult] = PluginRegistry()
    registry.register(MissingSecurityHeadersPlugin())
    registry.disable("web.missing-security-headers")

    web_config, scheduler_config = _configs()
    engine = WebAssessmentEngine(web_config, scheduler_config, registry)

    findings, _stats = await engine.run(f"{static_site}/index.html")

    assert not any(f.plugin_id == "web.missing-security-headers" for f in findings)
