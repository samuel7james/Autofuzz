"""Async worker pool: bounded concurrency, rate limiting, and retries.

Shared by both engines so neither reimplements its own throttling/retry
logic: Phase 4's web crawler and Phase 5's protocol fuzzer both submit jobs
here instead of opening connections directly, the way v1 did with a bare
synchronous loop.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from autofuzz.core.config import SchedulerConfig

T = TypeVar("T")


class RateLimiter:
    """Token-bucket limiter: at most ``rate_per_second`` acquisitions per second."""

    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._rate = rate_per_second
        self._capacity = max(1.0, rate_per_second)
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._updated_at
                self._updated_at = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                await asyncio.sleep((1 - self._tokens) / self._rate)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retries a failing async callable with exponential backoff and jitter."""

    max_retries: int
    backoff_seconds: float

    async def run(self, func: Callable[[], Awaitable[T]]) -> T:
        attempt = 0
        while True:
            try:
                return await func()
            except Exception:
                if attempt >= self.max_retries:
                    raise
                jitter = random.uniform(0, self.backoff_seconds)
                await asyncio.sleep(self.backoff_seconds * (2**attempt) + jitter)
                attempt += 1

    @classmethod
    def from_config(cls, config: SchedulerConfig) -> RetryPolicy:
        return cls(max_retries=config.max_retries, backoff_seconds=config.retry_backoff_seconds)


class WorkerPool(Generic[T]):
    """Runs a batch of async jobs under bounded concurrency, rate limiting, and retries."""

    def __init__(self, config: SchedulerConfig) -> None:
        self._config = config
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._rate_limiter = RateLimiter(config.rate_limit_per_second)
        self._retry_policy = RetryPolicy.from_config(config)

    async def _run_one(self, job: Callable[[], Awaitable[T]]) -> T:
        async def attempt() -> T:
            return await asyncio.wait_for(job(), timeout=self._config.request_timeout_seconds)

        async with self._semaphore:
            await self._rate_limiter.acquire()
            return await self._retry_policy.run(attempt)

    async def run_all(
        self,
        jobs: Sequence[Callable[[], Awaitable[T]]],
        *,
        on_job_done: Callable[[], None] | None = None,
    ) -> list[T | BaseException]:
        """Run all jobs concurrently; each result is either its return value or the
        exception it raised (after retries), in the same order as ``jobs``.

        If given, ``on_job_done`` fires the moment each individual job
        finishes (success or failure) - not once for the whole batch - so a
        caller can report fine-grained progress on a batch that takes a
        while, without waiting for every job in it to complete first. It
        does not affect the order-preserving return value: results are
        still collected via ``gather``, just from wrapped coroutines that
        each notify on their own completion before it resolves.
        """

        async def run_and_notify(job: Callable[[], Awaitable[T]]) -> T:
            try:
                return await self._run_one(job)
            finally:
                if on_job_done:
                    on_job_done()

        coros = (run_and_notify(job) for job in jobs)
        return list(await asyncio.gather(*coros, return_exceptions=True))
