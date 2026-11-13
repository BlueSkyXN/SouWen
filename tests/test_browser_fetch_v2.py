"""Deterministic tests for the in-process browser acquisition (SPEC 5/10)."""

from __future__ import annotations

import asyncio

import pytest

from souwen.common_runtime.provider_support import browser_fetch
from souwen.common_runtime.provider_support.browser_fetch import BrowserAcquisitionError


class _FakeResponse:
    status = 200

    async def all_headers(self):
        return {"content-type": "text/html; charset=utf-8"}


class _FakePage:
    def __init__(self, html: str, *, final_url: str | None = None) -> None:
        self._html = html
        self.url = final_url or "https://example.com/page"
        self.routed: list[str] = []

    async def route(self, pattern, handler):
        self._handler = handler

    async def goto(self, url, **kwargs):
        self.goto_url = url
        return _FakeResponse()

    async def content(self):
        return self._html

    async def title(self):
        return "Example"

    def locator(self, selector):
        return self

    async def inner_text(self):
        return self._html


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.url = url

    async def continue_(self):
        pass

    async def abort(self, reason):
        pass


def _patch_page(monkeypatch, page: _FakePage, *, resolver=None):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_validated(url, *, timeout_seconds, proxy):
        yield page, _FakeResponse()

    async def fake_resolver(url):
        if resolver is None:
            from souwen.common_runtime.security import ResolvedFetchTarget

            return (
                ResolvedFetchTarget(
                    original_url=url,
                    connect_url=url,
                    host_header="example.com",
                    sni_hostname=None,
                ),
                None,
            )
        return resolver(url)

    monkeypatch.setattr(browser_fetch, "_validated_page", fake_validated)
    monkeypatch.setattr(browser_fetch, "resolve_fetch_target_async", fake_resolver)


def test_fetch_page_html_returns_wrapped_outcome(monkeypatch) -> None:
    page = _FakePage("<html><body>results</body></html>")
    _patch_page(monkeypatch, page)

    outcome = asyncio.run(browser_fetch.fetch_page_html("https://example.com/page"))

    assert outcome.final_url == "https://example.com/page"
    assert "results" in outcome.content
    assert outcome.media_type == "text/html"


def test_fetch_page_content_extracts_text_and_metadata(monkeypatch) -> None:
    page = _FakePage("readable body text " * 20)
    _patch_page(monkeypatch, page)

    outcome = asyncio.run(
        browser_fetch.fetch_page_content("https://example.com/page", max_code_points=100)
    )

    assert outcome.truncated is True
    assert len(outcome.content) == 100
    assert outcome.media_type == "text/html"
    assert outcome.charset == "utf-8"


def test_blocked_initial_url_raises_policy(monkeypatch) -> None:
    async def blocking_resolver(url):
        return None, "private address"

    monkeypatch.setattr(browser_fetch, "resolve_fetch_target_async", blocking_resolver)

    with pytest.raises(BrowserAcquisitionError) as exc:
        asyncio.run(browser_fetch.fetch_page_html("http://127.0.0.1:8080/x"))
    assert exc.value.code == "policy_blocked"


def test_empty_content_maps_to_error(monkeypatch) -> None:
    page = _FakePage("")
    _patch_page(monkeypatch, page)

    with pytest.raises(BrowserAcquisitionError) as exc:
        asyncio.run(browser_fetch.fetch_page_html("https://example.com/empty"))
    assert exc.value.code == "empty_content"


def test_executor_maps_policy_and_returns_fetch_result(monkeypatch) -> None:
    from souwen.platform.provider_spi import (
        ExecutionContext,
        FetchTargetRequest,
        ProviderError,
        ProviderErrorCode,
        RequestContext,
    )
    from souwen.server.browser_executor import InProcessBrowserFetchExecutor

    page = _FakePage("real content " * 50)
    _patch_page(monkeypatch, page)

    executor = InProcessBrowserFetchExecutor(proxy_provider=lambda: None)
    request = FetchTargetRequest(target="https://example.com/page")
    result = asyncio.run(
        executor.fetch(request, RequestContext(request_id="t"), ExecutionContext.with_timeout(5))
    )
    assert result.status == "success"
    assert result.content_metadata.quality == "high"

    # robots 关闭浏览器路径：INVALID_REQUEST
    request_robots = FetchTargetRequest.model_validate(
        {"target": "https://example.com/page", "policy": {"respect_robots": True}}
    )
    with pytest.raises(ProviderError) as exc2:
        asyncio.run(
            executor.fetch(
                request_robots,
                RequestContext(request_id="t"),
                ExecutionContext.with_timeout(5),
            )
        )
    assert exc2.value.code is ProviderErrorCode.INVALID_REQUEST
