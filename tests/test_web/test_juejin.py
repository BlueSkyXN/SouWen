"""稀土掘金搜索客户端测试"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from souwen.models import SourceType, WebSearchResponse
from souwen.web.juejin import JuejinClient, _clean_html


class TestCleanHtml:
    """HTML 清理函数测试"""

    def test_removes_em_tags(self):
        assert _clean_html("<em>Python</em>") == "Python"

    def test_empty_string(self):
        assert _clean_html("") == ""

    def test_none_like(self):
        assert _clean_html(None) == ""


class TestJuejinClient:
    """JuejinClient 测试"""

    @pytest.fixture
    def client(self):
        return JuejinClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "juejin"

    def test_base_url(self, client):
        assert "api.juejin.cn" in client.BASE_URL

    @pytest.mark.asyncio
    async def test_search_success(self, client):
        """正常搜索返回结果"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "err_no": 0,
            "err_msg": "success",
            "data": [
                {
                    "result_model": {
                        "article_id": "7001",
                        "article_info": {
                            "title": "Python 异步编程",
                            "brief_content": "介绍 asyncio",
                            "digg_count": 42,
                            "view_count": 1200,
                            "comment_count": 5,
                            "ctime": "1700000000",
                        },
                        "author_user_info": {
                            "user_name": "张三",
                            "avatar_large": "",
                            "description": "",
                        },
                        "category": {"category_name": "后端"},
                        "tags": [
                            {"tag_name": "Python"},
                            {"tag_name": "异步"},
                        ],
                    },
                    "title_highlight": "<em>Python</em> 异步编程",
                    "content_highlight": "介绍 <em>asyncio</em> 的基本用法",
                },
            ],
            "cursor": "1",
            "has_more": False,
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("Python", max_results=10)

        assert isinstance(resp, WebSearchResponse)
        assert resp.source == SourceType.WEB_JUEJIN
        assert resp.query == "Python"
        assert len(resp.results) == 1
        assert resp.results[0].title == "Python 异步编程"
        assert resp.results[0].url == "https://juejin.cn/post/7001"
        assert "asyncio" in resp.results[0].snippet
        assert "后端" in resp.results[0].snippet
        assert "Python" in resp.results[0].snippet
        assert "张三" in resp.results[0].snippet
        assert resp.results[0].engine == "juejin"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client):
        """无结果时返回空列表"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "err_no": 0,
            "err_msg": "success",
            "data": [],
            "cursor": "0",
            "has_more": False,
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("xyznonexistent")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_api_error(self, client):
        """API 返回错误码时停止"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "err_no": 1,
            "err_msg": "param error",
            "data": None,
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("test")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_skips_invalid_items(self, client):
        """跳过缺少 article_id 或标题的条目"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "err_no": 0,
            "err_msg": "success",
            "data": [
                {
                    "result_model": {
                        "article_id": "",
                        "article_info": {
                            "title": "No ID",
                            "brief_content": "",
                            "digg_count": 0,
                            "view_count": 0,
                            "comment_count": 0,
                            "ctime": "0",
                        },
                        "author_user_info": {
                            "user_name": "",
                            "avatar_large": "",
                            "description": "",
                        },
                        "category": {"category_name": ""},
                        "tags": [],
                    },
                    "title_highlight": "No ID",
                    "content_highlight": "",
                },
                {
                    "result_model": {
                        "article_id": "7002",
                        "article_info": {
                            "title": "Valid",
                            "brief_content": "valid content",
                            "digg_count": 10,
                            "view_count": 100,
                            "comment_count": 0,
                            "ctime": "0",
                        },
                        "author_user_info": {
                            "user_name": "user",
                            "avatar_large": "",
                            "description": "",
                        },
                        "category": {"category_name": "前端"},
                        "tags": [{"tag_name": "React"}],
                    },
                    "title_highlight": "Valid",
                    "content_highlight": "valid content",
                },
            ],
            "cursor": "2",
            "has_more": False,
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("test")

        assert len(resp.results) == 1
        assert resp.results[0].title == "Valid"
        assert resp.results[0].url == "https://juejin.cn/post/7002"

    @pytest.mark.asyncio
    async def test_search_pagination_with_cursor(self, client):
        """cursor 分页正确工作"""
        page1_resp = MagicMock()
        page1_resp.json.return_value = {
            "err_no": 0,
            "err_msg": "success",
            "data": [
                {
                    "result_model": {
                        "article_id": f"100{i}",
                        "article_info": {
                            "title": f"Art{i}",
                            "brief_content": "",
                            "digg_count": 0,
                            "view_count": 0,
                            "comment_count": 0,
                            "ctime": "0",
                        },
                        "author_user_info": {
                            "user_name": "",
                            "avatar_large": "",
                            "description": "",
                        },
                        "category": {"category_name": ""},
                        "tags": [],
                    },
                    "title_highlight": f"Art{i}",
                    "content_highlight": "",
                }
                for i in range(3)
            ],
            "cursor": "3",
            "has_more": True,
        }
        page2_resp = MagicMock()
        page2_resp.json.return_value = {
            "err_no": 0,
            "err_msg": "success",
            "data": [
                {
                    "result_model": {
                        "article_id": f"200{i}",
                        "article_info": {
                            "title": f"Art2-{i}",
                            "brief_content": "",
                            "digg_count": 0,
                            "view_count": 0,
                            "comment_count": 0,
                            "ctime": "0",
                        },
                        "author_user_info": {
                            "user_name": "",
                            "avatar_large": "",
                            "description": "",
                        },
                        "category": {"category_name": ""},
                        "tags": [],
                    },
                    "title_highlight": f"Art2-{i}",
                    "content_highlight": "",
                }
                for i in range(2)
            ],
            "cursor": "5",
            "has_more": False,
        }

        with patch.object(
            client, "_fetch", new_callable=AsyncMock, side_effect=[page1_resp, page2_resp]
        ):
            resp = await client.search("test", max_results=5)

        assert len(resp.results) == 5

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client):
        """max_results 限制生效"""
        mock_response = MagicMock()
        items = [
            {
                "result_model": {
                    "article_id": str(i),
                    "article_info": {
                        "title": f"T{i}",
                        "brief_content": "",
                        "digg_count": 0,
                        "view_count": 0,
                        "comment_count": 0,
                        "ctime": "0",
                    },
                    "author_user_info": {"user_name": "", "avatar_large": "", "description": ""},
                    "category": {"category_name": ""},
                    "tags": [],
                },
                "title_highlight": f"T{i}",
                "content_highlight": "",
            }
            for i in range(20)
        ]
        mock_response.json.return_value = {
            "err_no": 0,
            "err_msg": "success",
            "data": items,
            "cursor": "20",
            "has_more": True,
        }

        with patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_response):
            resp = await client.search("test", max_results=5)

        assert len(resp.results) == 5

    @pytest.mark.asyncio
    async def test_search_handles_exception(self, client):
        """网络异常时返回空结果"""
        with patch.object(
            client, "_fetch", new_callable=AsyncMock, side_effect=Exception("timeout")
        ):
            resp = await client.search("test")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0
