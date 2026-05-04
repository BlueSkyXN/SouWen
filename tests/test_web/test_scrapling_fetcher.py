"""Scrapling fetch provider 单元测试。"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from souwen.config.models import SouWenConfig
from souwen.web.scrapling_fetcher import ScraplingFetcherClient


class _FakeSelectors(list):
    def get(self, default: str = "") -> str:
        return str(self[0]) if self else default

    def getall(self) -> list[str]:
        return [str(item) for item in self]


class _FakeElement:
    def __init__(self, text: str, html: str | None = None) -> None:
        self._text = text
        self._html = html or text

    def get_all_text(self, separator: str = "\n", strip: bool = True) -> str:
        del separator, strip
        return self._text

    def __str__(self) -> str:
        return self._html


class _FakePage:
    url = "https://example.com/final"
    status = 200
    reason = "OK"
    body = b"Example\nSelected body"
    html_content = (
        "<html><head><title>Example</title></head><body><main>Selected body</main></body></html>"
    )

    def css(self, selector: str) -> _FakeSelectors:
        if selector == "title::text":
            return _FakeSelectors(["Example"])
        if selector == "main":
            return _FakeSelectors([_FakeElement("Selected body", "<main>Selected body</main>")])
        return _FakeSelectors()

    def get_all_text(self, separator: str = "\n", strip: bool = True) -> str:
        del separator, strip
        return "Example\nSelected body"


class _FakeRobotsPage:
    url = "https://example.com/robots.txt"
    status = 200
    reason = "OK"
    body = b"User-agent: SouWenBot\nDisallow: /blocked\n"
    html_content = body.decode()


@pytest.fixture
def fake_scrapling_modules(monkeypatch):
    calls: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "fetcher": [],
        "dynamic": [],
        "stealthy": [],
    }

    class FakeAsyncFetcher:
        @staticmethod
        async def get(url: str, **kwargs: Any) -> _FakePage:
            calls["fetcher"].append((url, kwargs))
            if url.endswith("/robots.txt"):
                return _FakeRobotsPage()
            return _FakePage()

    class FakeDynamicFetcher:
        @staticmethod
        async def async_fetch(url: str, **kwargs: Any) -> _FakePage:
            calls["dynamic"].append((url, kwargs))
            return _FakePage()

    class FakeStealthyFetcher:
        @staticmethod
        async def async_fetch(url: str, **kwargs: Any) -> _FakePage:
            calls["stealthy"].append((url, kwargs))
            return _FakePage()

    scrapling_mod = types.ModuleType("scrapling")
    fetchers_mod = types.ModuleType("scrapling.fetchers")
    fetchers_mod.AsyncFetcher = FakeAsyncFetcher
    fetchers_mod.DynamicFetcher = FakeDynamicFetcher
    fetchers_mod.StealthyFetcher = FakeStealthyFetcher
    scrapling_mod.fetchers = fetchers_mod
    monkeypatch.setitem(sys.modules, "scrapling", scrapling_mod)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", fetchers_mod)
    return calls


@pytest.mark.asyncio
async def test_scrapling_fetcher_maps_selected_text_and_options(
    fake_scrapling_modules,
    monkeypatch,
):
    cfg = SouWenConfig(
        proxy="socks5://proxy.example:1080",
        sources={
            "scrapling": {
                "headers": {"X-Test": "1"},
                "params": {"impersonate": "chrome", "content_format": "text"},
            }
        },
    )
    monkeypatch.setattr("souwen.web.scrapling_fetcher.get_config", lambda: cfg)

    async with ScraplingFetcherClient() as client:
        result = await client.fetch(
            "https://example.com",
            timeout=4.5,
            selector="main",
            max_length=8,
        )

    assert result.error is None
    assert result.title == "Example"
    assert result.content == "Selected"
    assert result.content_truncated is True
    assert result.next_start_index == 8
    assert result.content_format == "text"
    assert result.final_url == "https://example.com/final"
    assert result.raw["mode"] == "fetcher"

    calls = fake_scrapling_modules["fetcher"]
    assert calls == [
        (
            "https://example.com",
            {
                "impersonate": "chrome",
                "timeout": 4.5,
                "headers": {"X-Test": "1"},
                "proxy": "socks5://proxy.example:1080",
            },
        )
    ]


@pytest.mark.asyncio
async def test_scrapling_dynamic_mode_uses_browser_timeout(fake_scrapling_modules, monkeypatch):
    cfg = SouWenConfig(
        sources={
            "scrapling": {
                "params": {
                    "mode": "dynamic",
                    "network_idle": True,
                    "content_format": "html",
                }
            }
        }
    )
    monkeypatch.setattr("souwen.web.scrapling_fetcher.get_config", lambda: cfg)

    async with ScraplingFetcherClient() as client:
        result = await client.fetch("https://example.com", timeout=3)

    assert result.error is None
    assert result.content_format == "html"
    assert result.content.startswith("<html>")
    assert fake_scrapling_modules["dynamic"] == [
        ("https://example.com", {"network_idle": True, "timeout": 3000})
    ]


@pytest.mark.asyncio
async def test_scrapling_batch_counts_partial_failures(fake_scrapling_modules, monkeypatch):
    cfg = SouWenConfig()
    monkeypatch.setattr("souwen.web.scrapling_fetcher.get_config", lambda: cfg)

    async with ScraplingFetcherClient() as client:
        original = client.fetch

        async def fake_fetch(url: str, **kwargs: Any):
            result = await original(url, **kwargs)
            if url.endswith("/fail"):
                return result.model_copy(update={"error": "boom", "content": ""})
            return result

        monkeypatch.setattr(client, "fetch", fake_fetch)
        resp = await client.fetch_batch(["https://example.com/ok", "https://example.com/fail"])

    assert resp.provider == "scrapling"
    assert resp.total == 2
    assert resp.total_ok == 1
    assert resp.total_failed == 1


@pytest.mark.asyncio
async def test_scrapling_respect_robots_blocks_disallowed_url(
    fake_scrapling_modules,
    monkeypatch,
):
    class FakeRobotsParser:
        def can_fetch(self, url: str, user_agent: str) -> bool:
            return user_agent == "SouWenBot/1.0" and not url.endswith("/blocked")

    class FakeProtego:
        @staticmethod
        def parse(text: str) -> FakeRobotsParser:
            assert "Disallow: /blocked" in text
            return FakeRobotsParser()

    protego_mod = types.ModuleType("protego")
    protego_mod.Protego = FakeProtego
    monkeypatch.setitem(sys.modules, "protego", protego_mod)
    monkeypatch.setattr("souwen.web.fetch.validate_fetch_url", lambda url: (True, ""))
    monkeypatch.setattr("souwen.web.scrapling_fetcher.get_config", lambda: SouWenConfig())

    async with ScraplingFetcherClient() as client:
        result = await client.fetch(
            "https://example.com/blocked",
            respect_robots_txt=True,
        )

    assert result.error == "robots.txt 拒绝抓取（UA=SouWenBot/1.0）"
    assert result.raw == {"provider": "scrapling", "blocked_by_robots": True}
    assert fake_scrapling_modules["fetcher"] == [
        (
            "https://example.com/robots.txt",
            {
                "timeout": 10.0,
                "follow_redirects": "safe",
                "retries": 1,
                "headers": {"User-Agent": "SouWenBot/1.0"},
            },
        )
    ]
