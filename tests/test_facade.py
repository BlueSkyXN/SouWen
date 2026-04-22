"""``souwen.facade`` 子模块委托语义测试。

facade 层是 V1 对外暴露的统一入口，本身不实现业务逻辑，只把请求按 domain
/ capability / provider 派发给底层 adapter 或 ``souwen.web.*`` 实现。本文件
通过 monkeypatch 把底层模块替换成内存桩，验证 facade 在参数透传、provider
校验、registry 派发等方面是否正确委托。

测试清单：
- ``TestFacadeSearch``：``facade.search`` 派发到正确的 adapter
- ``TestFacadeFetch``：``facade.fetch`` 校验 provider 并委托给 web.fetch
- ``TestFacadeArchive``：``facade.archive`` 委托给 ``WaybackClient``
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import sys

import souwen.facade.archive  # noqa: F401  ensure submodule registered
import souwen.facade.fetch  # noqa: F401
import souwen.facade.search  # noqa: F401

# souwen.facade.__init__ exposes a function named ``search`` that shadows the
# submodule attribute; grab the real submodules from sys.modules instead.
facade_search = sys.modules["souwen.facade.search"]
facade_fetch = sys.modules["souwen.facade.fetch"]
facade_archive = sys.modules["souwen.facade.archive"]

from souwen.models import FetchResponse, FetchResult, SearchResponse  # noqa: E402


# ---------------------------------------------------------------------------
# facade.search
# ---------------------------------------------------------------------------


class TestFacadeSearch:
    """``facade.search`` 派发到 ``_execute_search`` 的语义。"""


    async def test_search_dispatches_with_resolved_adapters(self, monkeypatch):
        """``search()`` 应先 ``_select_adapters``，再透传给 ``_execute_search``。"""
        captured: dict[str, Any] = {}
        sentinel_adapter = SimpleNamespace(name="dummy")

        def fake_select(domain, capability, sources):
            captured["select"] = (domain, capability, sources)
            return [sentinel_adapter]

        async def fake_execute(domain, query, adapters, limit, capability, **kw):
            captured["execute"] = {
                "domain": domain,
                "query": query,
                "adapters": adapters,
                "limit": limit,
                "capability": capability,
                "kwargs": kw,
            }
            return [SearchResponse(query=query, source="openalex", results=[])]

        monkeypatch.setattr(facade_search, "_select_adapters", fake_select)
        monkeypatch.setattr(facade_search, "_execute_search", fake_execute)

        out = await facade_search.search(
            "transformers", domain="paper", capability="search", limit=7
        )
        assert len(out) == 1
        assert captured["select"] == ("paper", "search", None)
        assert captured["execute"]["adapters"] == [sentinel_adapter]
        assert captured["execute"]["limit"] == 7
        assert captured["execute"]["capability"] == "search"


    async def test_search_papers_targets_paper_domain(self, monkeypatch):
        """``search_papers()`` 必须以 domain=paper / capability=search 派发。"""
        captured: dict[str, Any] = {}

        async def fake_search(query, domain="paper", capability="search",
                              sources=None, limit=10, **kw):
            captured["args"] = (query, domain, capability, sources, limit)
            return []

        monkeypatch.setattr(facade_search, "search", fake_search)
        await facade_search.search_papers("LLM", per_page=5)
        assert captured["args"] == ("LLM", "paper", "search", None, 5)


    async def test_search_patents_targets_patent_domain(self, monkeypatch):
        """``search_patents()`` 必须以 domain=patent / capability=search 派发。"""
        captured: dict[str, Any] = {}

        async def fake_search(query, domain="paper", capability="search",
                              sources=None, limit=10, **kw):
            captured["args"] = (query, domain, capability, sources, limit)
            return []

        monkeypatch.setattr(facade_search, "search", fake_search)
        await facade_search.search_patents("battery", per_page=3)
        assert captured["args"] == ("battery", "patent", "search", None, 3)


# ---------------------------------------------------------------------------
# facade.fetch
# ---------------------------------------------------------------------------


class TestFacadeFetch:
    """``facade.fetch`` 对底层 ``souwen.web.fetch.fetch_content`` 的委托。"""


    async def test_fetch_content_delegates_to_web_fetch(self, monkeypatch):
        """合法 provider 时应直接转发 urls/timeout/kwargs 到 web.fetch。"""
        captured: dict[str, Any] = {}

        # 让 registry 视为存在该 provider 且支持 fetch capability。
        # facade.fetch 通过 ``from souwen.registry import get as _registry_get``
        # 引用，需要替换 facade 模块自身持有的别名。
        adapter_stub = SimpleNamespace(
            name="builtin", capabilities={"fetch"}
        )
        monkeypatch.setattr(
            facade_fetch, "_registry_get", lambda name: adapter_stub
        )

        async def fake_impl(urls, provider="builtin", timeout=30.0, **kw):
            captured["call"] = {
                "urls": list(urls),
                "provider": provider,
                "timeout": timeout,
                "kwargs": kw,
            }
            return FetchResponse(
                urls=list(urls),
                results=[FetchResult(url=urls[0], final_url=urls[0])],
                total=1,
                total_ok=1,
                provider=provider,
            )

        # facade.fetch 在函数体内 from souwen.web.fetch import fetch_content
        # 因此打桩到源模块上才能生效。
        import souwen.web.fetch as web_fetch_mod

        monkeypatch.setattr(web_fetch_mod, "fetch_content", fake_impl)

        resp = await facade_fetch.fetch_content(
            ["https://example.com"], provider="builtin", timeout=12.5
        )
        assert isinstance(resp, FetchResponse)
        assert captured["call"]["urls"] == ["https://example.com"]
        assert captured["call"]["provider"] == "builtin"
        assert captured["call"]["timeout"] == 12.5


    async def test_fetch_unknown_provider_raises(self, monkeypatch):
        """registry 中找不到 provider 应抛 ValueError。"""
        monkeypatch.setattr(facade_fetch, "_registry_get", lambda name: None)
        with pytest.raises(ValueError, match="unknown fetch provider"):
            await facade_fetch.fetch_content(
                ["https://example.com"], provider="nope-nope"
            )


    async def test_fetch_provider_without_fetch_capability_raises(
        self, monkeypatch
    ):
        """provider 存在但未声明 fetch capability 时应抛 ValueError。"""
        adapter_stub = SimpleNamespace(
            name="paper-only", capabilities={"search"}
        )
        monkeypatch.setattr(
            facade_fetch, "_registry_get", lambda name: adapter_stub
        )
        with pytest.raises(ValueError, match="不支持 fetch"):
            await facade_fetch.fetch_content(
                ["https://example.com"], provider="paper-only"
            )


# ---------------------------------------------------------------------------
# facade.archive
# ---------------------------------------------------------------------------


class _FakeWaybackClient:
    """把 ``WaybackClient`` 全部 await 接口替换成可记录的内存桩。"""

    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def query_snapshots(self, *args, **kwargs):
        self.calls.append(("query_snapshots", args, kwargs))
        return ["snap"]

    async def check_availability(self, *args, **kwargs):
        self.calls.append(("check_availability", args, kwargs))
        return {"available": True}

    async def save_page(self, *args, **kwargs):
        self.calls.append(("save_page", args, kwargs))
        return {"job": "ok"}

    async def fetch(self, *args, **kwargs):
        self.calls.append(("fetch", args, kwargs))
        return {"content": "stub"}


@pytest.fixture()
def patched_wayback(monkeypatch):
    """把 ``souwen.web.wayback.WaybackClient`` 替换成共享的 fake 实例工厂。"""
    instance = _FakeWaybackClient()

    import souwen.web.wayback as wb_mod

    def factory(*args, **kwargs):
        return instance

    monkeypatch.setattr(wb_mod, "WaybackClient", factory)
    return instance


class TestFacadeArchive:
    """``facade.archive`` 各入口应正确委托给 ``WaybackClient`` 的对应方法。"""


    async def test_archive_lookup_calls_query_snapshots(self, patched_wayback):
        out = await facade_archive.archive_lookup(
            "https://example.com", from_date="20200101", to_date="20231231"
        )
        assert out == ["snap"]
        method, args, kwargs = patched_wayback.calls[-1]
        assert method == "query_snapshots"
        assert args == ("https://example.com",)
        assert kwargs == {"from_date": "20200101", "to_date": "20231231"}


    async def test_archive_check_calls_check_availability(self, patched_wayback):
        out = await facade_archive.archive_check(
            "https://example.com", timestamp="20210101", timeout=15.0
        )
        assert out == {"available": True}
        method, args, kwargs = patched_wayback.calls[-1]
        assert method == "check_availability"
        assert args == ("https://example.com",)
        assert kwargs == {"timestamp": "20210101", "timeout": 15.0}


    async def test_archive_save_calls_save_page(self, patched_wayback):
        out = await facade_archive.archive_save(
            "https://example.com", timeout=45.0
        )
        assert out == {"job": "ok"}
        method, args, kwargs = patched_wayback.calls[-1]
        assert method == "save_page"
        assert args == ("https://example.com",)
        assert kwargs == {"timeout": 45.0}


    async def test_archive_fetch_calls_fetch(self, patched_wayback):
        out = await facade_archive.archive_fetch(
            "https://example.com", timeout=20.0
        )
        assert out == {"content": "stub"}
        method, args, kwargs = patched_wayback.calls[-1]
        assert method == "fetch"
        assert args == ("https://example.com",)
        assert kwargs == {"timeout": 20.0}
