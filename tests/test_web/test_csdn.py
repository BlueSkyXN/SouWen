"""CSDN 搜索客户端测试"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from souwen.models import WebSearchResponse
from souwen.web.csdn import CSDNClient, _clean_html


class TestCleanHtml:
    """HTML 清理函数测试"""

    def test_removes_em_tags(self):
        assert _clean_html("<em>Python</em> 教程") == "Python 教程"

    def test_removes_nested_tags(self):
        assert _clean_html("<span class='x'><em>A</em></span>") == "A"

    def test_empty_string(self):
        assert _clean_html("") == ""

    def test_none_like(self):
        assert _clean_html(None) == ""

    def test_plain_text_unchanged(self):
        assert _clean_html("hello world") == "hello world"


class TestCSDNClient:
    """CSDNClient 测试"""

    @pytest.fixture
    def client(self):
        return CSDNClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "csdn"

    def test_base_url(self, client):
        assert "so.csdn.net" in client.BASE_URL

    @pytest.mark.asyncio
    async def test_search_success(self, client):
        """正常搜索返回结果"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result_vos": [
                {
                    "title": "<em>Python</em> 异步编程",
                    "url_location": "https://blog.csdn.net/user1/article/details/123",
                    "digest": "介绍 <em>Python</em> asyncio 基础用法",
                    "nickname": "张三",
                },
                {
                    "title": "FastAPI 入门教程",
                    "url_location": "https://blog.csdn.net/user2/article/details/456",
                    "digest": "FastAPI 框架快速上手指南",
                    "nickname": "李四",
                },
            ]
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("Python", max_results=10)

        assert isinstance(resp, WebSearchResponse)
        assert resp.source == "csdn"
        assert resp.query == "Python"
        assert len(resp.results) == 2
        assert resp.results[0].title == "Python 异步编程"
        assert resp.results[0].url == "https://blog.csdn.net/user1/article/details/123"
        assert "Python asyncio" in resp.results[0].snippet
        assert "张三" in resp.results[0].snippet
        assert resp.results[0].engine == "csdn"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client):
        """无结果时返回空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"result_vos": []}

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("xyznonexistent123456")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_no_result_vos_key(self, client):
        """API 返回缺少 result_vos 键时返回空"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "message": "success"}

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("test")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_skips_invalid_items(self, client):
        """跳过缺少标题或 URL 的条目"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result_vos": [
                {"title": "", "url_location": "http://x.com", "digest": "x", "nickname": ""},
                {"title": "Valid", "url_location": "", "digest": "y", "nickname": ""},
                {
                    "title": "Good Title",
                    "url_location": "https://blog.csdn.net/valid",
                    "digest": "Good content",
                    "nickname": "Author",
                },
            ]
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("test")

        assert len(resp.results) == 1
        assert resp.results[0].title == "Good Title"

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client):
        """max_results 限制生效"""
        items = [
            {
                "title": f"Article {i}",
                "url_location": f"https://blog.csdn.net/article/{i}",
                "digest": f"Content {i}",
                "nickname": f"User{i}",
            }
            for i in range(30)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"result_vos": items}

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("test", max_results=5)

        assert len(resp.results) == 5

    @pytest.mark.asyncio
    async def test_search_handles_exception(self, client):
        """网络异常时返回空结果"""
        with patch.object(
            client, "_fetch", new_callable=AsyncMock, side_effect=Exception("Network error")
        ):
            resp = await client.search("test")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_pagination(self, client):
        """多页请求时正确分页"""
        page1_items = [
            {
                "title": f"P1-{i}",
                "url_location": f"https://csdn.net/{i}",
                "digest": f"d{i}",
                "nickname": "",
            }
            for i in range(20)
        ]
        page2_items = [
            {
                "title": f"P2-{i}",
                "url_location": f"https://csdn.net/p2-{i}",
                "digest": f"d{i}",
                "nickname": "",
            }
            for i in range(5)
        ]

        resp1 = MagicMock()
        resp1.json.return_value = {"result_vos": page1_items}
        resp2 = MagicMock()
        resp2.json.return_value = {"result_vos": page2_items}

        with patch.object(client, "_fetch", new_callable=AsyncMock, side_effect=[resp1, resp2]):
            resp = await client.search("test", max_results=25)

        assert len(resp.results) == 25
