"""Tests for the lazy Playwright browser pool."""

from __future__ import annotations

import builtins
import sys
import types
from typing import Any

import pytest

from souwen.config.models import SouWenConfig
from souwen.core.browser_pool import (
    BrowserPoolKey,
    PlaywrightBrowserPool,
    close_browser_pools,
    get_browser_pool,
)
from souwen.core.exceptions import ConfigError


class _FakePage:
    pass


class _FakeContext:
    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options
        self.closed = False
        self.page = _FakePage()

    async def new_page(self) -> _FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.closed = False

    def is_connected(self) -> bool:
        return not self.closed

    async def new_context(self, **kwargs: Any) -> _FakeContext:
        context = _FakeContext(kwargs)
        self.state["contexts"].append(context)
        return context

    async def close(self) -> None:
        self.closed = True


class _FakeBrowserType:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    async def launch(self, **kwargs: Any) -> _FakeBrowser:
        self.state["launches"].append(kwargs)
        browser = _FakeBrowser(self.state)
        self.state["browsers"].append(browser)
        return browser


class _FakePlaywright:
    def __init__(self, state: dict[str, Any]) -> None:
        self.chromium = _FakeBrowserType(state)
        self.state = state
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True
        self.state["stopped"] = True


class _FakePlaywrightManager:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state

    async def start(self) -> _FakePlaywright:
        playwright = _FakePlaywright(self.state)
        self.state["playwright"] = playwright
        return playwright


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "launches": [],
        "contexts": [],
        "browsers": [],
        "stopped": False,
    }
    playwright_mod = types.ModuleType("playwright")
    async_api_mod = types.ModuleType("playwright.async_api")
    async_api_mod.async_playwright = lambda: _FakePlaywrightManager(state)
    monkeypatch.setitem(sys.modules, "playwright", playwright_mod)
    monkeypatch.setitem(sys.modules, "playwright.async_api", async_api_mod)
    return state


@pytest.mark.asyncio
async def test_browser_pool_lazily_reuses_browser_and_closes_context(monkeypatch):
    state = _install_fake_playwright(monkeypatch)
    pool = PlaywrightBrowserPool(
        BrowserPoolKey(proxy="http://proxy.example:8080"),
        max_pages=1,
    )

    assert pool.started is False

    async with pool.page(
        user_agent="SouWen Test Browser",
        extra_http_headers={"Accept-Language": "en-US"},
    ) as page:
        assert isinstance(page, _FakePage)

    async with pool.page(user_agent="SouWen Test Browser"):
        pass

    assert len(state["launches"]) == 1
    assert state["launches"][0] == {
        "headless": True,
        "proxy": {"server": "http://proxy.example:8080"},
    }
    assert len(state["contexts"]) == 2
    assert state["contexts"][0].options["user_agent"] == "SouWen Test Browser"
    assert state["contexts"][0].options["extra_http_headers"] == {"Accept-Language": "en-US"}
    assert all(context.closed for context in state["contexts"])

    await pool.close()
    assert state["browsers"][0].closed is True
    assert state["stopped"] is True
    assert pool.started is False


@pytest.mark.asyncio
async def test_get_browser_pool_reuses_per_loop_and_resolved_proxy(monkeypatch):
    cfg = SouWenConfig(proxy="http://global-proxy.example:8080")
    monkeypatch.setattr("souwen.core.browser_pool.get_config", lambda: cfg)

    pool1 = get_browser_pool(source_name="google_patents", max_pages=1)
    pool2 = get_browser_pool(source_name="google_patents", max_pages=1)

    assert pool1 is pool2
    assert pool1.key.proxy == "http://global-proxy.example:8080"

    await close_browser_pools()


@pytest.mark.asyncio
async def test_browser_pool_missing_playwright_raises_config_error(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "playwright.async_api":
            raise ImportError("missing playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pool = PlaywrightBrowserPool(max_pages=1)

    with pytest.raises(ConfigError) as exc:
        async with pool.page():
            pass

    assert "playwright" in str(exc.value)
