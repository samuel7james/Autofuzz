"""Unit tests for the HttpClient config wiring (Phase 4)."""

from __future__ import annotations

from autofuzz.core.config import SchedulerConfig, WebEngineConfig
from autofuzz.web.http_client import HttpClient


async def test_http_client_applies_configured_user_agent_and_redirects() -> None:
    web_config = WebEngineConfig(user_agent="TestAgent/1.0", follow_redirects=False)
    scheduler_config = SchedulerConfig(request_timeout_seconds=7.0)

    async with HttpClient(web_config, scheduler_config) as client:
        assert client._client.headers["user-agent"] == "TestAgent/1.0"
        assert client._client.follow_redirects is False
        assert client._client.timeout.connect == 7.0


async def test_http_client_closes_underlying_client() -> None:
    web_config = WebEngineConfig()
    scheduler_config = SchedulerConfig()

    client = HttpClient(web_config, scheduler_config)
    await client.aclose()

    assert client._client.is_closed
