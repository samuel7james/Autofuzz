"""Async HTTP client wrapper for the Web Assessment Engine.

Wraps ``httpx.AsyncClient`` with AutoFuzz's config model (timeout, user
agent, redirect policy) so the crawler and discovery modules never touch
httpx directly — one seam for request/response behavior instead of each
caller configuring its own client.
"""

from __future__ import annotations

from types import TracebackType

import httpx

from autofuzz.core.config import SchedulerConfig, WebEngineConfig


class HttpClient:
    """Thin async wrapper around ``httpx.AsyncClient``, configured from AutoFuzz profiles."""

    def __init__(
        self,
        web_config: WebEngineConfig,
        scheduler_config: SchedulerConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=scheduler_config.request_timeout_seconds,
            follow_redirects=web_config.follow_redirects,
            headers={"User-Agent": web_config.user_agent},
            transport=transport,
        )

    async def get(self, url: str) -> httpx.Response:
        return await self._client.get(url)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
