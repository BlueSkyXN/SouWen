"""Fake-Playwright tests for pinning, policy, output bounds, and cleanup."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from souwen.common_runtime.security import ResolvedFetchTarget
from souwen.worker.browser_fetch.executor import BrowserExecutionError, PlaywrightBrowserExecutor
from souwen.worker.browser_fetch.protocol import WorkerFetchRequest


def _resolved(url: str, address: str = "1.1.1.1") -> ResolvedFetchTarget:
    return ResolvedFetchTarget(
        original_url=url,
        connect_url=url.replace("example.com", address),
        host_header="example.com",
        sni_hostname="example.com",
    )


class _Route:
    def __init__(self) -> None:
        self.continued = 0
        self.aborted = 0

    async def continue_(self) -> None:
        self.continued += 1

    async def abort(self, _reason: str) -> None:
        self.aborted += 1


class _Request:
    def __init__(self, url: str) -> None:
        self.url = url


class _Response:
    status = 200

    async def all_headers(self):
        return {"content-type": "text/html; charset=utf-8"}


class _Locator:
    def __init__(self, page) -> None:
        self.page = page

    async def inner_text(self) -> str:
        return self.page.content


class _Page:
    def __init__(self, *, content: str, cross_origin: bool = False, delay: float = 0) -> None:
        self.content = content
        self.cross_origin = cross_origin
        self.delay = delay
        self.url = "https://example.com/page"
        self.handler = None

    async def route(self, _pattern: str, handler) -> None:
        self.handler = handler

    async def goto(self, url: str, **_kwargs):
        self.url = url
        if self.delay:
            await asyncio.sleep(self.delay)
        route = _Route()
        await self.handler(route, _Request(url))
        if self.cross_origin:
            await self.handler(route, _Request("https://other.example/redirect"))
            if route.aborted:
                raise RuntimeError("raw browser redirect failure")
            self.url = "https://other.example/redirect"
        return _Response()

    def locator(self, _selector: str) -> _Locator:
        return _Locator(self)

    async def title(self) -> str:
        return "Rendered"


class _Pool:
    def __init__(self, key, page: _Page, state: dict[str, object]) -> None:
        self.key = key
        self._page = page
        self._state = state
        self._closed = False

    @property
    def started(self) -> bool:
        return not self._closed

    @asynccontextmanager
    async def page(self, **options):
        self._state["context_options"] = options
        try:
            yield self._page
        finally:
            self._state["context_closed"] = True

    async def close(self) -> None:
        self._closed = True
        self._state["pool_closed"] = True


@pytest.mark.asyncio
async def test_executor_pins_host_revalidates_requests_and_bounds_output() -> None:
    calls = []

    async def resolver(url: str):
        calls.append(url)
        return _resolved(url), ""

    state: dict[str, object] = {}
    page = _Page(content="x" * 80)

    def factory(key):
        state["key"] = key
        return _Pool(key, page, state)

    executor = PlaywrightBrowserExecutor(
        resolver=resolver,
        pool_factory=factory,
        clock=lambda: datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    item = await executor.execute(
        WorkerFetchRequest(target="https://example.com/page", max_code_points=70),
        timeout_seconds=2,
    )

    assert state["key"].proxy is None
    assert state["key"].host_resolver_rules == ()
    assert state["context_options"]["accept_downloads"] is False
    assert state["context_options"]["service_workers"] == "block"
    assert state["context_options"]["proxy"].startswith("http://127.0.0.1:")
    assert calls == [
        "https://example.com/page",
        "https://example.com/page",
        "https://example.com/page",
    ]
    assert item.content == "x" * 70
    assert item.truncated is True
    assert item.quality == "high"
    assert state["context_closed"] is True
    assert "pool_closed" not in state
    await executor.close()
    assert state["pool_closed"] is True


@pytest.mark.asyncio
async def test_executor_rejects_cross_origin_redirect_without_raw_error() -> None:
    async def resolver(url: str):
        if "other.example" in url:
            return None, "blocked"
        return _resolved(url), ""

    state: dict[str, object] = {}
    executor = PlaywrightBrowserExecutor(
        resolver=resolver,
        pool_factory=lambda key: _Pool(key, _Page(content="ok", cross_origin=True), state),
    )

    with pytest.raises(BrowserExecutionError) as caught:
        await executor.execute(
            WorkerFetchRequest(target="https://example.com/page"),
            timeout_seconds=2,
        )

    assert caught.value.code == "policy_blocked"
    assert "raw" not in str(caught.value)
    assert state["context_closed"] is True
    await executor.close()
    assert state["pool_closed"] is True


@pytest.mark.asyncio
async def test_executor_allows_cross_origin_only_after_independent_revalidation() -> None:
    calls = []

    async def resolver(url: str):
        calls.append(url)
        address = "1.0.0.1" if "other.example" in url else "1.1.1.1"
        hostname = "other.example" if "other.example" in url else "example.com"
        return (
            ResolvedFetchTarget(
                original_url=url,
                connect_url=url.replace(hostname, address),
                host_header=hostname,
                sni_hostname=hostname,
            ),
            "",
        )

    state: dict[str, object] = {}
    executor = PlaywrightBrowserExecutor(
        resolver=resolver,
        pool_factory=lambda key: _Pool(key, _Page(content="rendered", cross_origin=True), state),
    )

    item = await executor.execute(
        WorkerFetchRequest(target="https://example.com/page"),
        timeout_seconds=2,
    )

    assert str(item.final_url) == "https://other.example/redirect"
    assert calls.count("https://other.example/redirect") == 2
    await executor.close()


@pytest.mark.asyncio
async def test_executor_timeout_closes_context_without_background_page() -> None:
    async def resolver(url: str):
        return _resolved(url), ""

    state: dict[str, object] = {}
    executor = PlaywrightBrowserExecutor(
        resolver=resolver,
        pool_factory=lambda key: _Pool(key, _Page(content="ok", delay=1), state),
    )

    with pytest.raises(BrowserExecutionError) as caught:
        await executor.execute(
            WorkerFetchRequest(target="https://example.com/page"),
            timeout_seconds=0.01,
        )

    assert caught.value.code == "worker_timeout"
    assert state["context_closed"] is True
    assert "pool_closed" not in state
    await executor.close()
    assert state["pool_closed"] is True


@pytest.mark.asyncio
async def test_executor_readiness_initializes_and_reuses_one_browser_pool() -> None:
    async def resolver(url: str):
        return _resolved(url), ""

    state: dict[str, object] = {}
    factory_calls = []

    def factory(key):
        factory_calls.append(key)
        return _Pool(key, _Page(content="rendered"), state)

    executor = PlaywrightBrowserExecutor(resolver=resolver, pool_factory=factory)

    await executor.initialize()
    await executor.execute(
        WorkerFetchRequest(target="https://example.com/page"),
        timeout_seconds=2,
    )

    assert executor.ready is True
    assert len(factory_calls) == 1
    assert "pool_closed" not in state
    await executor.close()
    assert executor.ready is False
    assert state["pool_closed"] is True
