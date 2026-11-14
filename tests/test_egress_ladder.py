"""Deterministic tests for the egress ladder (SPEC 5.1-5.3, 5.5)."""

from __future__ import annotations

import asyncio

import pytest

from souwen.common_runtime.egress import (
    EgressLevel,
    EgressMemory,
    EgressPlanner,
    egress_bounds_for,
)
from souwen.common_runtime.provider_support.exceptions import (
    RateLimitError,
    SourceUnavailableError,
)


def test_bounds_default_and_browser_capable() -> None:
    default = egress_bounds_for("arxiv")
    assert default.min_level is EgressLevel.IMPERSONATE
    assert default.max_level is EgressLevel.PROXY

    browser = egress_bounds_for("baidu")
    assert browser.max_level is EgressLevel.BROWSER


def test_memory_starts_at_min_and_climbs_after_failure() -> None:
    memory = EgressMemory(clock=lambda: 0.0)
    bounds = egress_bounds_for("baidu")

    assert memory.next_level("example.com", bounds) is EgressLevel.IMPERSONATE
    memory.remember_failure("example.com", EgressLevel.IMPERSONATE)
    assert memory.next_level("example.com", bounds) is EgressLevel.PROXY
    # PROXY 成功后成为记忆中的起点
    memory.remember_success("example.com", EgressLevel.PROXY)
    assert memory.next_level("example.com", bounds) is EgressLevel.PROXY
    # PROXY 新失败 → 跳过一次，升到 BROWSER
    memory.remember_failure("example.com", EgressLevel.PROXY)
    assert memory.next_level("example.com", bounds) is EgressLevel.BROWSER


def test_planner_skips_unavailable_levels() -> None:
    memory = EgressMemory(clock=lambda: 0.0)
    bounds = egress_bounds_for("duckduckgo")
    memory.remember_failure("example.com", EgressLevel.IMPERSONATE)
    memory.remember_failure("example.com", EgressLevel.PROXY)
    planner = EgressPlanner(
        memory,
        proxy_provider=lambda: None,
        browser_available=lambda: False,
    )

    decision = planner.plan("example.com", bounds)

    # SPEC 5.5：浏览器缺失时阶梯在前三级内工作；无代理时 PROXY 不可执行，
    # 有效天花板是 IMPERSONATE，不假称使用了更高级别。
    assert decision.level is EgressLevel.IMPERSONATE
    assert decision.reason == "remembered-or-min"


def test_planner_uses_proxy_when_configured() -> None:
    memory = EgressMemory(clock=lambda: 0.0)
    bounds = egress_bounds_for("arxiv")
    memory.remember_failure("api.example.org", EgressLevel.IMPERSONATE)
    planner = EgressPlanner(
        memory,
        proxy_provider=lambda: "socks5://localhost:1080",
        browser_available=lambda: False,
    )

    decision = planner.plan("api.example.org", bounds)

    assert decision.level is EgressLevel.PROXY
    assert decision.proxy == "socks5://localhost:1080"


def test_planner_ceiling_respects_max_level() -> None:
    memory = EgressMemory(clock=lambda: 0.0)
    bounds = egress_bounds_for("arxiv")  # max = PROXY
    memory.remember_failure("api.example.org", EgressLevel.IMPERSONATE)
    planner = EgressPlanner(
        memory,
        proxy_provider=lambda: None,
        browser_available=lambda: True,
    )

    decision = planner.plan("api.example.org", bounds)

    # SPEC 5.5：无代理时 PROXY 不可执行，有效天花板降到 IMPERSONATE
    assert decision.level is EgressLevel.IMPERSONATE
    assert planner.effective_bounds(bounds).max_level is EgressLevel.IMPERSONATE


def test_effective_bounds_lower_ceiling_without_browser() -> None:
    memory = EgressMemory(clock=lambda: 0.0)
    bounds = egress_bounds_for("duckduckgo")  # max = BROWSER
    planner = EgressPlanner(
        memory,
        proxy_provider=lambda: "socks5://localhost:1080",
        browser_available=lambda: False,
    )

    # Chromium 缺失：browser 级不参与，天花板回到 PROXY
    assert planner.effective_bounds(bounds).max_level is EgressLevel.PROXY


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}
        self.extensions: dict[str, str] = {}


class _ScraperHarness:
    """Drive BaseScraper._fetch with a fake _do_request per level."""

    def __init__(self, monkeypatch, engine_name: str, behavior: dict) -> None:
        from souwen.common_runtime.provider_support.scraper.base import BaseScraper
        from souwen.common_runtime.egress import EgressMemory

        self.calls: list[str] = []
        self.memory = EgressMemory(clock=lambda: 0.0)

        class _Scraper(BaseScraper):
            ENGINE_NAME = engine_name

        scraper = _Scraper(min_delay=0, max_delay=0, max_retries=1, follow_redirects=False)
        scraper._egress_planner = EgressPlanner(
            self.memory,
            proxy_provider=lambda: behavior.get("proxy_url"),
            browser_available=lambda: False,
        )
        self.behavior = behavior
        self.scraper = scraper

        async def fake_do_request(method, url, params, headers, data=None, *, egress_level=None):
            label = getattr(egress_level, "label", "legacy")
            self.calls.append(label)
            outcome = behavior.get(label)
            if outcome == "fail":
                raise SourceUnavailableError(f"simulated failure at {label}")
            if outcome == "rate":
                raise RateLimitError("simulated rate limit")
            return _FakeResponse()

        monkeypatch.setattr(scraper, "_do_request", fake_do_request)

    def fetch(self, url: str = "https://example.com/search?q=x"):
        return asyncio.run(self.scraper._fetch(url))


def test_scraper_fetch_climbs_on_failure_and_tags_success(monkeypatch) -> None:
    harness = _ScraperHarness(
        monkeypatch,
        "baidu",
        {"impersonate": "fail", "proxy": "ok", "proxy_url": "socks5://localhost:1080"},
    )

    resp = harness.fetch()

    assert harness.calls == ["impersonate", "proxy"]
    assert resp.extensions["souwen_egress"] == "proxy"
    assert harness.memory.status("example.com")["best_level"] == "proxy"


def test_scraper_fetch_succeeds_without_climbing(monkeypatch) -> None:
    harness = _ScraperHarness(monkeypatch, "arxiv", {"impersonate": "ok"})

    resp = harness.fetch()

    assert harness.calls == ["impersonate"]
    assert resp.extensions["souwen_egress"] == "impersonate"


def test_scraper_fetch_raises_after_exhausting_climbs(monkeypatch) -> None:
    harness = _ScraperHarness(
        monkeypatch,
        "arxiv",
        {"impersonate": "fail", "proxy": "fail", "proxy_url": "socks5://localhost:1080"},
    )

    with pytest.raises(SourceUnavailableError):
        harness.fetch()

    assert harness.calls == ["impersonate", "proxy"]


def test_scraper_fetch_rate_limit_eligible_for_climb(monkeypatch) -> None:
    harness = _ScraperHarness(
        monkeypatch,
        "arxiv",
        {"impersonate": "rate", "proxy": "ok", "proxy_url": "socks5://localhost:1080"},
    )

    resp = harness.fetch()

    assert harness.calls == ["impersonate", "proxy"]
    assert resp.extensions["souwen_egress"] == "proxy"


def test_scraper_fetch_403_response_counts_as_failure(monkeypatch) -> None:
    from souwen.common_runtime.provider_support.scraper.base import BaseScraper
    from souwen.common_runtime.egress import EgressMemory

    memory = EgressMemory(clock=lambda: 0.0)
    calls: list[str] = []

    class _Scraper(BaseScraper):
        ENGINE_NAME = "bing"

    scraper = _Scraper(min_delay=0, max_delay=0, max_retries=1, follow_redirects=False)
    scraper._egress_planner = EgressPlanner(
        memory,
        proxy_provider=lambda: "socks5://localhost:1080",
        browser_available=lambda: False,
    )

    async def fake_do_request(method, url, params, headers, data=None, *, egress_level=None):
        label = getattr(egress_level, "label", "legacy")
        calls.append(label)
        if label == "impersonate":
            return _FakeResponse(status_code=403)
        return _FakeResponse()

    scraper._do_request = fake_do_request  # type: ignore[method-assign]

    resp = asyncio.run(scraper._fetch("https://www.bing.com/search?q=x"))

    assert calls == ["impersonate", "proxy"]
    assert resp.extensions["souwen_egress"] == "proxy"


def test_resolved_target_climbs_direct_to_proxy_via_override(monkeypatch) -> None:
    """解析请求（IP-pin 路径）接入阶梯：直连被拒后经 proxy_override 用代理重试。

    builtin 正文抓取走 _fetch(_resolved_target=...)；此前该路径完全绕过
    planner，直连失败不会升级（复核 20261114 3.2 指出）。
    """

    from souwen.common_runtime.provider_support.scraper.base import BaseScraper
    from souwen.common_runtime.egress import EgressMemory
    from souwen.common_runtime.security import ResolvedFetchTarget

    memory = EgressMemory(clock=lambda: 0.0)
    seen_overrides: list[str | None] = []

    class _Scraper(BaseScraper):
        ENGINE_NAME = "bing"

    scraper = _Scraper(min_delay=0, max_delay=0, max_retries=1, follow_redirects=False)
    scraper._proxy = "socks5://localhost:1080"
    scraper._egress_planner = EgressPlanner(
        memory,
        proxy_provider=lambda: "socks5://localhost:1080",
        browser_available=lambda: False,
    )

    async def fake_resolved(
        method, target, params, headers, data=None, *, proxy_override=None, _max_response_bytes=None
    ):  # noqa: E501
        seen_overrides.append(proxy_override)
        # 第一跳（IMPERSRONATE 探测，显式直连 ""）被拒；PROXY 级带代理成功
        if proxy_override == "":
            return _FakeResponse(status_code=403)
        return _FakeResponse()

    scraper._do_resolved_request = fake_resolved  # type: ignore[method-assign]

    target = ResolvedFetchTarget(
        original_url="https://www.bing.com/page",
        connect_url="https://1.1.1.1/page",
        host_header="www.bing.com",
        sni_hostname="www.bing.com",
    )

    resp = asyncio.run(scraper._fetch("https://www.bing.com/page", _resolved_target=target))

    # 第一跳直连（显式空串覆盖默认代理），失败后升级 PROXY 用真代理
    assert seen_overrides == ["", "socks5://localhost:1080"]
    assert resp.extensions["souwen_egress"] == "proxy"


def test_resolved_target_without_proxy_falls_back_to_legacy_retry(monkeypatch) -> None:
    """无代理时解析请求起步级即天花板：保持 legacy 重试语义（不进阶梯）。"""

    from souwen.common_runtime.provider_support.scraper.base import BaseScraper
    from souwen.common_runtime.egress import EgressMemory
    from souwen.common_runtime.security import ResolvedFetchTarget

    memory = EgressMemory(clock=lambda: 0.0)
    calls: list[str | None] = []

    class _Scraper(BaseScraper):
        ENGINE_NAME = "arxiv"

    scraper = _Scraper(min_delay=0, max_delay=0, max_retries=2, follow_redirects=False)
    scraper._proxy = None
    scraper._egress_planner = EgressPlanner(
        memory,
        proxy_provider=lambda: None,
        browser_available=lambda: False,
    )

    async def fake_resolved(
        method, target, params, headers, data=None, *, proxy_override=None, _max_response_bytes=None
    ):  # noqa: E501
        calls.append(proxy_override)
        if len(calls) == 1:
            return _FakeResponse(status_code=500)
        return _FakeResponse()

    scraper._do_resolved_request = fake_resolved  # type: ignore[method-assign]

    async def no_delay() -> None:
        return None

    scraper._polite_delay = no_delay  # type: ignore[method-assign]

    import souwen.common_runtime.provider_support.scraper.base as base_module

    real_sleep = base_module.asyncio.sleep

    async def fast_sleep(_delay: float) -> None:
        return None

    base_module.asyncio.sleep = fast_sleep
    try:
        target = ResolvedFetchTarget(
            original_url="https://arxiv.org/abs/1",
            connect_url="https://1.1.1.1/abs/1",
            host_header="arxiv.org",
            sni_hostname="arxiv.org",
        )
        resp = asyncio.run(scraper._fetch("https://arxiv.org/abs/1", _resolved_target=target))
    finally:
        base_module.asyncio.sleep = real_sleep

    # legacy 循环：默认 proxy_override（None → self._proxy），500 重试后成功
    assert calls == [None, None]
    assert resp.status_code == 200
