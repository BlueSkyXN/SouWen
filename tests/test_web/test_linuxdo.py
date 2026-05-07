"""LinuxDo 论坛搜索客户端测试"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from souwen.models import WebSearchResponse
from souwen.web.linuxdo import LinuxDoClient, _clean_html


class TestCleanHtml:
    """HTML 清理函数测试"""

    def test_removes_span_highlight(self):
        assert _clean_html('<span class="search-highlight">Python</span>') == "Python"

    def test_empty_string(self):
        assert _clean_html("") == ""

    def test_none_like(self):
        assert _clean_html(None) == ""

    def test_plain_text(self):
        assert _clean_html("hello") == "hello"


class TestLinuxDoClient:
    """LinuxDoClient 测试"""

    @pytest.fixture
    def client(self):
        return LinuxDoClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "linuxdo"

    def test_base_url(self, client):
        assert client.BASE_URL == "https://linux.do"

    @pytest.mark.asyncio
    async def test_search_success_posts_and_topics(self, client):
        """正常搜索：posts 关联 topics，生成正确 URL"""
        mock_json = {
            "topics": [
                {
                    "id": 100,
                    "title": "Discourse 插件开发指南",
                    "slug": "discourse-plugin-guide",
                    "posts_count": 15,
                    "like_count": 8,
                },
                {
                    "id": 200,
                    "title": "Linux 内核调试技巧",
                    "slug": "linux-kernel-debug",
                    "posts_count": 5,
                    "like_count": 3,
                },
            ],
            "posts": [
                {
                    "id": 1001,
                    "topic_id": 100,
                    "post_number": 3,
                    "blurb": "推荐使用 <span>ember</span> 框架",
                    "username": "dev_user",
                    "like_count": 5,
                },
                {
                    "id": 1002,
                    "topic_id": 200,
                    "post_number": 1,
                    "blurb": "内核调试的几个常用工具",
                    "username": "linux_fan",
                    "like_count": 0,
                },
            ],
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("plugin", max_results=10)

        assert isinstance(resp, WebSearchResponse)
        assert resp.source == "linuxdo"
        assert resp.query == "plugin"
        assert len(resp.results) == 2

        # 第一条来自 posts[0]，关联 topic 100
        r0 = resp.results[0]
        assert r0.title == "Discourse 插件开发指南"
        assert r0.url == "https://linux.do/t/discourse-plugin-guide/100/3"
        assert "ember" in r0.snippet
        assert "@dev_user" in r0.snippet
        assert "👍5" in r0.snippet

        # 第二条来自 posts[1]，关联 topic 200
        r1 = resp.results[1]
        assert r1.title == "Linux 内核调试技巧"
        assert r1.url == "https://linux.do/t/linux-kernel-debug/200/1"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client):
        """无结果时返回空列表"""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"topics": [], "posts": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("xyznonexistent")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_fills_from_topics_when_posts_insufficient(self, client):
        """posts 不足时从 topics 补充"""
        mock_json = {
            "topics": [
                {
                    "id": 300,
                    "title": "Topic Only",
                    "slug": "topic-only",
                    "posts_count": 10,
                    "like_count": 2,
                },
            ],
            "posts": [],
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("topic", max_results=5)

        assert len(resp.results) == 1
        assert resp.results[0].title == "Topic Only"
        assert resp.results[0].url == "https://linux.do/t/topic-only/300"
        assert "回复: 10" in resp.results[0].snippet

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self, client):
        """max_results 限制生效"""
        topics = [
            {"id": i, "title": f"Topic {i}", "slug": f"t-{i}", "posts_count": 1, "like_count": 0}
            for i in range(10)
        ]
        posts = [
            {
                "id": i + 100,
                "topic_id": i,
                "post_number": 1,
                "blurb": f"blurb {i}",
                "username": "u",
                "like_count": 0,
            }
            for i in range(10)
        ]

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"topics": topics, "posts": posts}
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("test", max_results=3)

        assert len(resp.results) == 3

    @pytest.mark.asyncio
    async def test_search_handles_network_error(self, client):
        """网络异常时返回空结果"""
        with patch.object(
            client._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("failed")
        ):
            resp = await client.search("test")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_handles_http_error(self, client):
        """HTTP 错误状态码时返回空结果"""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=MagicMock(), response=MagicMock()
        )

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("test")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_no_slug_fallback(self, client):
        """topic 无 slug 时 URL 回退格式"""
        mock_json = {
            "topics": [
                {
                    "id": 500,
                    "title": "No Slug Topic",
                    "slug": "",
                    "posts_count": 1,
                    "like_count": 0,
                },
            ],
            "posts": [
                {
                    "id": 5001,
                    "topic_id": 500,
                    "post_number": 2,
                    "blurb": "content",
                    "username": "u",
                    "like_count": 0,
                },
            ],
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("test")

        assert resp.results[0].url == "https://linux.do/t/500/2"

    @pytest.mark.asyncio
    async def test_search_skips_post_without_topic(self, client):
        """post 对应的 topic 不在返回中时跳过"""
        mock_json = {
            "topics": [],
            "posts": [
                {
                    "id": 9999,
                    "topic_id": 8888,
                    "post_number": 1,
                    "blurb": "orphan",
                    "username": "u",
                    "like_count": 0,
                },
            ],
        }

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = mock_json
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            resp = await client.search("test")

        # topic 不在映射中，标题为空，所以被跳过
        assert len(resp.results) == 0
