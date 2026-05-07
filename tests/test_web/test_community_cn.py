"""中文社区聚合搜索客户端测试"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from souwen.models import WebSearchResponse, WebSearchResult
from souwen.web.community_cn import (
    CommunityCnClient,
    PLATFORM_DOMAINS,
    _build_site_query,
    _label_snippet,
)


# ── 辅助函数测试 ────────────────────────────────────────────


class TestBuildSiteQuery:
    """site: 搜索词构造测试"""

    def test_basic(self):
        assert _build_site_query("Python", "v2ex.com") == "site:v2ex.com Python"

    def test_chinese_query(self):
        assert _build_site_query("异步编程", "linux.do") == "site:linux.do 异步编程"

    def test_empty_query(self):
        assert _build_site_query("", "hostloc.com") == "site:hostloc.com "


class TestLabelSnippet:
    """snippet 标签添加测试"""

    def test_adds_prefix(self):
        assert _label_snippet("好帖子", "V2EX") == "[V2EX] 好帖子"

    def test_no_double_prefix(self):
        assert _label_snippet("[V2EX] 好帖子", "V2EX") == "[V2EX] 好帖子"

    def test_empty_snippet(self):
        assert _label_snippet("", "LinuxDo") == "[LinuxDo] "


class TestPlatformDomains:
    """平台常量测试"""

    def test_has_required_platforms(self):
        required = {
            "linux.do",
            "nodeseek.com",
            "hostloc.com",
            "v2ex.com",
            "coolapk.com",
            "xiaohongshu.com",
        }
        assert required == set(PLATFORM_DOMAINS.keys())

    def test_labels_non_empty(self):
        for domain, label in PLATFORM_DOMAINS.items():
            assert label, f"{domain} 的标签不应为空"


# ── Client 测试 ─────────────────────────────────────────────


def _make_ddg_response(items: list[dict], query: str = "test") -> WebSearchResponse:
    """构造模拟的 DuckDuckGo 搜索响应"""
    results = [
        WebSearchResult(
            source="duckduckgo",
            title=item["title"],
            url=item["url"],
            snippet=item.get("snippet", ""),
            engine="duckduckgo",
            raw={},
        )
        for item in items
    ]
    return WebSearchResponse(
        query=query,
        source="duckduckgo",
        total_results=len(results),
        results=results,
    )


class TestCommunityCnClient:
    """CommunityCnClient 测试"""

    @pytest.fixture
    def client(self):
        return CommunityCnClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "community_cn"

    @pytest.mark.asyncio
    async def test_search_aggregates_platforms(self, client):
        """正常搜索：聚合多个平台结果"""
        mock_ddg = AsyncMock()

        # 每个平台返回 1 条结果
        async def fake_search(query, max_results=20, max_pages=1):
            for domain in PLATFORM_DOMAINS:
                if f"site:{domain}" in query:
                    return _make_ddg_response(
                        [
                            {
                                "title": f"Post on {domain}",
                                "url": f"https://{domain}/post/1",
                                "snippet": "content",
                            }
                        ],
                        query=query,
                    )
            return _make_ddg_response([], query=query)

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("Python", max_results=20)

        assert isinstance(resp, WebSearchResponse)
        assert resp.source == "community_cn"
        assert resp.query == "Python"
        assert len(resp.results) == len(PLATFORM_DOMAINS)

        # 每条结果都有平台标签
        for r in resp.results:
            assert r.source == "community_cn"
            assert r.engine.startswith("community_cn:")
            assert r.snippet.startswith("[")

    @pytest.mark.asyncio
    async def test_search_deduplicates_by_url(self, client):
        """URL 去重：相同 URL 只保留一次"""
        mock_ddg = AsyncMock()

        async def fake_search(query, max_results=20, max_pages=1):
            # 所有平台都返回同一个 URL
            return _make_ddg_response(
                [{"title": "Same", "url": "https://example.com/dup", "snippet": "dup"}],
                query=query,
            )

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("test", max_results=20)

        assert len(resp.results) == 1
        assert resp.results[0].url == "https://example.com/dup"

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client):
        """max_results 限制生效"""
        mock_ddg = AsyncMock()

        call_count = 0

        async def fake_search(query, max_results=20, max_pages=1):
            nonlocal call_count
            call_count += 1
            return _make_ddg_response(
                [
                    {
                        "title": f"R{call_count}-1",
                        "url": f"https://example.com/{call_count}/1",
                        "snippet": "a",
                    },
                    {
                        "title": f"R{call_count}-2",
                        "url": f"https://example.com/{call_count}/2",
                        "snippet": "b",
                    },
                    {
                        "title": f"R{call_count}-3",
                        "url": f"https://example.com/{call_count}/3",
                        "snippet": "c",
                    },
                ],
                query=query,
            )

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("test", max_results=5)

        assert len(resp.results) <= 5

    @pytest.mark.asyncio
    async def test_search_resilient_to_platform_failure(self, client):
        """单平台失败不影响其他平台"""
        mock_ddg = AsyncMock()

        call_idx = 0

        async def fake_search(query, max_results=20, max_pages=1):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                raise ConnectionError("network down")
            return _make_ddg_response(
                [{"title": f"OK-{call_idx}", "url": f"https://ok.com/{call_idx}", "snippet": "ok"}],
                query=query,
            )

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("test", max_results=20)

        assert isinstance(resp, WebSearchResponse)
        # 至少有部分结果（不是全部失败）
        assert len(resp.results) >= 1

    @pytest.mark.asyncio
    async def test_search_all_platforms_fail(self, client):
        """所有平台都失败时返回空结果"""
        mock_ddg = AsyncMock()

        async def fake_search(query, max_results=20, max_pages=1):
            raise Exception("all down")

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("test")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0
        assert resp.source == "community_cn"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client):
        """所有平台无结果时返回空列表"""
        mock_ddg = AsyncMock()

        async def fake_search(query, max_results=20, max_pages=1):
            return _make_ddg_response([], query=query)

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("xyznonexistent123456")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_result_engine_includes_domain(self, client):
        """结果的 engine 字段包含来源域名"""
        mock_ddg = AsyncMock()

        async def fake_search(query, max_results=20, max_pages=1):
            if "site:v2ex.com" in query:
                return _make_ddg_response(
                    [{"title": "V2EX Post", "url": "https://v2ex.com/t/123", "snippet": "topic"}],
                    query=query,
                )
            return _make_ddg_response([], query=query)

        mock_ddg.search = fake_search
        client._ddg_client = mock_ddg

        resp = await client.search("Python")

        v2ex_results = [r for r in resp.results if r.engine == "community_cn:v2ex.com"]
        assert len(v2ex_results) == 1
        assert v2ex_results[0].engine == "community_cn:v2ex.com"
