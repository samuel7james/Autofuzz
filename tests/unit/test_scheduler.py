"""Unit tests for the async worker pool: concurrency, rate limiting, retries."""

from __future__ import annotations

import asyncio

import pytest

from autofuzz.core.config import SchedulerConfig
from autofuzz.core.scheduler import RateLimiter, RetryPolicy, WorkerPool


async def test_worker_pool_runs_all_jobs_and_preserves_order() -> None:
    config = SchedulerConfig(concurrency=3, rate_limit_per_second=1000, max_retries=0)
    pool: WorkerPool[int] = WorkerPool(config)

    async def job(n: int) -> int:
        await asyncio.sleep(0)
        return n * 2

    jobs = [lambda n=i: job(n) for i in range(5)]
    results = await pool.run_all(jobs)

    assert results == [0, 2, 4, 6, 8]


async def test_worker_pool_respects_concurrency_limit() -> None:
    config = SchedulerConfig(concurrency=2, rate_limit_per_second=1000, max_retries=0)
    pool: WorkerPool[None] = WorkerPool(config)

    active = 0
    max_active = 0

    async def job() -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1

    await pool.run_all([job for _ in range(6)])

    assert max_active <= 2


async def test_worker_pool_returns_exceptions_instead_of_raising() -> None:
    config = SchedulerConfig(concurrency=2, rate_limit_per_second=1000, max_retries=0)
    pool: WorkerPool[None] = WorkerPool(config)

    async def failing_job() -> None:
        raise ValueError("boom")

    results = await pool.run_all([failing_job])

    assert len(results) == 1
    assert isinstance(results[0], ValueError)


async def test_retry_policy_retries_up_to_max_then_raises() -> None:
    policy = RetryPolicy(max_retries=2, backoff_seconds=0.001)
    attempts = 0

    async def always_fails() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await policy.run(always_fails)

    assert attempts == 3  # initial attempt + 2 retries


async def test_retry_policy_succeeds_after_transient_failure() -> None:
    policy = RetryPolicy(max_retries=3, backoff_seconds=0.001)
    attempts = 0

    async def fails_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("transient")
        return "ok"

    result = await policy.run(fails_once)

    assert result == "ok"
    assert attempts == 2


async def test_rate_limiter_throttles_beyond_capacity() -> None:
    limiter = RateLimiter(rate_per_second=10)
    loop = asyncio.get_event_loop()

    start = loop.time()
    for _ in range(10):
        await limiter.acquire()
    assert loop.time() - start < 0.5  # within capacity: fast

    start = loop.time()
    await limiter.acquire()  # exceeds capacity: must wait ~1/10s
    assert loop.time() - start > 0.03


def test_rate_limiter_rejects_non_positive_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(rate_per_second=0)
