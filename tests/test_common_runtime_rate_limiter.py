"""Canonical Common Runtime rate-limiter identity and cancellation conformance."""

from __future__ import annotations

import ast
import asyncio
from collections import deque
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

import souwen.common_runtime.resilience.rate_limiter as canonical_module
from souwen.common_runtime.resilience import (
    RateLimiterBase,
    SlidingWindowLimiter,
    TokenBucketLimiter,
)
from souwen.core import rate_limiter as legacy_module
from souwen.paper import openalex
from souwen.patent import the_lens


def test_legacy_rate_limiters_reexport_canonical_objects() -> None:
    assert legacy_module.RateLimiterBase is RateLimiterBase
    assert legacy_module.TokenBucketLimiter is TokenBucketLimiter
    assert legacy_module.SlidingWindowLimiter is SlidingWindowLimiter
    assert RateLimiterBase.__module__ == "souwen.common_runtime.resilience.rate_limiter"
    assert TokenBucketLimiter.__module__ == "souwen.common_runtime.resilience.rate_limiter"
    assert SlidingWindowLimiter.__module__ == "souwen.common_runtime.resilience.rate_limiter"


def test_canonical_module_is_stdlib_only_and_legacy_defines_no_classes() -> None:
    canonical_path = Path(canonical_module.__file__)
    canonical_tree = ast.parse(
        canonical_path.read_text(encoding="utf-8"), filename=str(canonical_path)
    )
    imported = {
        node.module
        for node in ast.walk(canonical_tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(canonical_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert imported == {"__future__", "abc", "asyncio", "collections", "time"}

    legacy_path = Path(legacy_module.__file__)
    legacy_tree = ast.parse(legacy_path.read_text(encoding="utf-8"), filename=str(legacy_path))
    assert not any(isinstance(node, ast.ClassDef) for node in legacy_tree.body)


async def _wait_until_cancelled(started: asyncio.Event, delays: list[float], delay: float) -> None:
    delays.append(delay)
    started.set()
    await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_token_bucket_cancellation_releases_lock_and_preserves_pre_sleep_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = TokenBucketLimiter(rate=1.0, burst=1)
    limiter._tokens = 0.0
    limiter._last_refill = 100.0
    started = asyncio.Event()
    delays: list[float] = []
    monkeypatch.setattr(canonical_module.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        canonical_module.asyncio,
        "sleep",
        lambda delay: _wait_until_cancelled(started, delays, delay),
    )

    task = asyncio.create_task(limiter.acquire())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert delays == [1.0]
    assert not limiter._lock.locked()
    assert limiter._tokens == 0.0
    assert limiter._last_refill == 100.0

    limiter._tokens = 1.0
    await limiter.acquire()
    assert limiter._tokens == 0.0


@pytest.mark.asyncio
async def test_retry_pause_cancellation_preserves_pause_and_next_acquire_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60.0)
    monkeypatch.setattr(canonical_module.time, "monotonic", lambda: 100.0)
    limiter.update_from_headers(remaining=0, retry_after=5.0)
    started = asyncio.Event()
    delays: list[float] = []
    monkeypatch.setattr(
        canonical_module.asyncio,
        "sleep",
        lambda delay: _wait_until_cancelled(started, delays, delay),
    )

    task = asyncio.create_task(limiter.acquire())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert delays == [5.0]
    assert not limiter._lock.locked()
    assert limiter._retry_until == 105.0
    assert limiter.max_requests == 10
    assert list(limiter._timestamps) == []

    monkeypatch.setattr(canonical_module.time, "monotonic", lambda: 106.0)
    await limiter.acquire()
    assert limiter._retry_until == 0
    assert limiter.max_requests == 10
    assert list(limiter._timestamps) == [106.0]


@pytest.mark.asyncio
async def test_window_wait_cancellation_preserves_timestamps_and_releases_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = SlidingWindowLimiter(max_requests=1, window_seconds=60.0)
    limiter._timestamps = deque([100.0])
    monkeypatch.setattr(canonical_module.time, "monotonic", lambda: 100.0)
    started = asyncio.Event()
    delays: list[float] = []
    monkeypatch.setattr(
        canonical_module.asyncio,
        "sleep",
        lambda delay: _wait_until_cancelled(started, delays, delay),
    )

    task = asyncio.create_task(limiter.acquire())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert delays == [60.01]
    assert not limiter._lock.locked()
    assert list(limiter._timestamps) == [100.0]

    monkeypatch.setattr(canonical_module.time, "monotonic", lambda: 161.0)
    await limiter.acquire()
    assert list(limiter._timestamps) == [161.0]


def test_representative_consumers_use_canonical_limiter_classes() -> None:
    assert openalex.TokenBucketLimiter is TokenBucketLimiter
    assert the_lens.SlidingWindowLimiter is SlidingWindowLimiter


def test_the_lens_keeps_header_parsing_outside_common_runtime() -> None:
    client = object.__new__(the_lens.TheLensClient)
    client._limiter = Mock()
    response = httpx.Response(
        200,
        headers={
            "x-rate-limit-remaining-request-per-minute": "7",
            "x-rate-limit-retry-after-seconds": "2.5",
        },
    )

    client._update_rate_limit(response)

    client._limiter.update_from_headers.assert_called_once_with(
        remaining=7,
        retry_after=2.5,
    )
    canonical_source = Path(canonical_module.__file__).read_text(encoding="utf-8").lower()
    assert "x-rate-limit-remaining-request-per-minute" not in canonical_source
    assert "x-rate-limit-retry-after-seconds" not in canonical_source
