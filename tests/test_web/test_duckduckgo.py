"""DuckDuckGo 网页搜索客户端测试"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from souwen.models import WebSearchResponse
from souwen.web.duckduckgo import DuckDuckGoClient


# 模拟 DDG HTML 响应
MOCK_HTML_PAGE = b"""
<html>
<body>
<div class="results">
  <div><h2><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage1&amp;rut=abc">
    First Result Title
  </a></h2>
  <a class="result__snippet">This is the first result description</a>
  </div>
  <div><h2><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage2&amp;rut=def">
    Second Result Title
  </a></h2>
  <a class="result__snippet">This is the second result description</a>
  </div>
</div>
</body>
</html>
"""

MOCK_HTML_NO_RESULTS = b"""
<html><body>
<div class="no-results">No  results.</div>
</body></html>
"""

MOCK_HTML_WITH_NEXT = b"""
<html><body>
<div><h2><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fr1">Title 1</a></h2>
<a class="result__snippet">Snippet 1</a></div>
<div class="nav-link"><form>
<input type="hidden" name="q" value="test"/>
<input type="hidden" name="s" value="30"/>
<input type="hidden" name="dc" value="31"/>
<input type="hidden" name="nextParams" value="abc"/>
<input type="submit" value="Next"/>
</form></div>
</body></html>
"""


class TestDuckDuckGoClient:
    """DuckDuckGoClient 测试"""

    @pytest.fixture
    def client(self):
        return DuckDuckGoClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "duckduckgo"

    def test_base_url(self, client):
        assert client.BASE_URL == "https://html.duckduckgo.com/html/"

    def test_low_delay(self, client):
        assert client.min_delay == 0.75
        assert client.max_delay == 1.5

    def test_follow_redirects_disabled(self, client):
        assert client._follow_redirects is False

    @pytest.mark.asyncio
    async def test_search_success(self, client):
        """正常搜索返回结果"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_HTML_PAGE

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp):
            resp = await client.search("test query")

        assert isinstance(resp, WebSearchResponse)
        assert resp.source == "duckduckgo"
        assert resp.query == "test query"
        assert len(resp.results) == 2
        assert resp.results[0].title == "First Result Title"
        assert resp.results[0].url == "https://example.com/page1"
        assert "first result description" in resp.results[0].snippet

    @pytest.mark.asyncio
    async def test_search_no_results(self, client):
        """无结果时返回空"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_HTML_NO_RESULTS

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp):
            resp = await client.search("xyznonexist")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_rate_limited(self, client):
        """反爬信号停止分页"""
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp):
            resp = await client.search("test")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client):
        """max_results 限制"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_HTML_PAGE

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp):
            resp = await client.search("test", max_results=1)

        assert len(resp.results) == 1

    @pytest.mark.asyncio
    async def test_search_exception_handled(self, client):
        """网络异常不崩溃"""
        with patch.object(
            client, "_fetch", new_callable=AsyncMock, side_effect=Exception("network")
        ):
            resp = await client.search("test")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_pagination(self, client):
        """分页：第一页有 next form，第二页无"""
        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.content = MOCK_HTML_WITH_NEXT

        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.content = MOCK_HTML_PAGE  # 无 next form

        with patch.object(
            client, "_fetch", new_callable=AsyncMock, side_effect=[page1_resp, page2_resp]
        ):
            resp = await client.search("test", max_results=10)

        # page1 有 1 结果 + page2 有 2 结果
        assert len(resp.results) == 3

    @pytest.mark.asyncio
    async def test_search_deduplicates(self, client):
        """相同 URL 去重"""
        # 两页返回同样的内容
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_HTML_PAGE

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp):
            resp = await client.search("test", max_results=10, max_pages=1)

        # 同一页内 URL 不重复
        urls = [r.url for r in resp.results]
        assert len(urls) == len(set(urls))

    def test_decode_ddg_url(self):
        """URL 解码"""
        encoded = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftest&rut=abc"
        assert DuckDuckGoClient._decode_ddg_url(encoded) == "https://example.com/test"

    def test_decode_ddg_url_passthrough(self):
        """非重定向 URL 原样返回"""
        url = "https://example.com/direct"
        assert DuckDuckGoClient._decode_ddg_url(url) == url

    @pytest.mark.asyncio
    async def test_search_with_region_and_time(self, client):
        """参数传递验证"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = MOCK_HTML_PAGE

        with patch.object(
            client, "_fetch", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_fetch:
            await client.search("test", region="cn-zh", time_range="w")

        # 验证 POST 调用中包含正确的 data
        call_kwargs = mock_fetch.call_args
        assert call_kwargs.kwargs["data"]["kl"] == "cn-zh"
        assert call_kwargs.kwargs["data"]["df"] == "w"
        assert call_kwargs.kwargs["method"] == "POST"
