"""DuckDuckGo News / Images / Videos 客户端测试"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from souwen.models import WebSearchResponse
from souwen.web.ddg_news import DuckDuckGoNewsClient
from souwen.web.ddg_images import DuckDuckGoImagesClient, ImageSearchResponse
from souwen.web.ddg_videos import DuckDuckGoVideosClient, VideoSearchResponse
from souwen.web.ddg_utils import extract_vqd, normalize_text, normalize_url, parse_next_offset


class TestDDGUtils:
    """共享工具函数测试"""

    def test_extract_vqd_double_quote(self):
        html = b'some html vqd="abc123" more html'
        assert extract_vqd(html, "test") == "abc123"

    def test_extract_vqd_single_quote(self):
        html = b"some html vqd='xyz789' more html"
        assert extract_vqd(html, "test") == "xyz789"

    def test_extract_vqd_ampersand(self):
        html = b"some html vqd=token456&other=1 more"
        assert extract_vqd(html, "test") == "token456"

    def test_extract_vqd_json(self):
        html = b'{"vqd":"json_vqd_value"}'
        assert extract_vqd(html, "test") == "json_vqd_value"

    def test_extract_vqd_none(self):
        html = b"no vqd here"
        assert extract_vqd(html, "test") is None

    def test_normalize_text(self):
        assert normalize_text("<b>Hello</b> <em>World</em>") == "Hello World"

    def test_normalize_text_empty(self):
        assert normalize_text("") == ""

    def test_normalize_url(self):
        assert normalize_url("https%3A%2F%2Fexample.com") == "https://example.com"

    def test_parse_next_offset(self):
        assert parse_next_offset("i.js?s=100&o=json") == "100"

    def test_parse_next_offset_none(self):
        assert parse_next_offset(None) is None
        assert parse_next_offset("no-s-param") is None


class TestDuckDuckGoNewsClient:
    """新闻搜索客户端测试"""

    @pytest.fixture
    def client(self):
        return DuckDuckGoNewsClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "duckduckgo_news"

    @pytest.mark.asyncio
    async def test_search_no_vqd(self, client):
        """VQD 获取失败返回空"""
        with patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value=None):
            resp = await client.search("test")

        assert isinstance(resp, WebSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_success(self, client):
        """正常搜索"""
        mock_json = {
            "results": [
                {
                    "title": "Breaking News",
                    "url": "https://news.example.com/1",
                    "excerpt": "<b>Important</b> event",
                    "source": "ExampleNews",
                    "date": 1700000000,
                },
                {
                    "title": "Tech Update",
                    "url": "https://tech.example.com/2",
                    "excerpt": "New <em>release</em>",
                    "source": "TechBlog",
                    "date": 1700100000,
                },
            ],
            "next": None,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="vqd123"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("news test")

        assert resp.source == "duckduckgo_news"
        assert len(resp.results) == 2
        assert resp.results[0].title == "Breaking News"
        assert "ExampleNews" in resp.results[0].snippet
        assert "Important event" in resp.results[0].snippet

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client):
        """空结果"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [], "next": None}

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="vqd123"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("nothing")

        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_deduplicates_urls(self, client):
        """URL 去重"""
        mock_json = {
            "results": [
                {"title": "A", "url": "https://same.com", "excerpt": "", "source": "", "date": 0},
                {"title": "B", "url": "https://same.com", "excerpt": "", "source": "", "date": 0},
            ],
            "next": None,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="v"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("test")

        assert len(resp.results) == 1


class TestDuckDuckGoImagesClient:
    """图片搜索客户端测试"""

    @pytest.fixture
    def client(self):
        return DuckDuckGoImagesClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "duckduckgo_images"

    @pytest.mark.asyncio
    async def test_search_no_vqd(self, client):
        with patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value=None):
            resp = await client.search("test")

        assert isinstance(resp, ImageSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_success(self, client):
        """正常图片搜索"""
        mock_json = {
            "results": [
                {
                    "title": "Cat Photo",
                    "url": "https://example.com/cat",
                    "image": "https://cdn.example.com/cat.jpg",
                    "thumbnail": "https://cdn.example.com/cat_thumb.jpg",
                    "width": 1920,
                    "height": 1080,
                    "source": "Unsplash",
                },
            ],
            "next": None,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="vqd"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("cat")

        assert len(resp.results) == 1
        r = resp.results[0]
        assert r.title == "Cat Photo"
        assert r.image_url == "https://cdn.example.com/cat.jpg"
        assert r.width == 1920
        assert r.height == 1080
        assert r.image_source == "Unsplash"

    @pytest.mark.asyncio
    async def test_search_deduplicates_images(self, client):
        """相同图片 URL 去重"""
        mock_json = {
            "results": [
                {
                    "title": "A",
                    "url": "u1",
                    "image": "https://same.jpg",
                    "thumbnail": "",
                    "width": 0,
                    "height": 0,
                    "source": "",
                },
                {
                    "title": "B",
                    "url": "u2",
                    "image": "https://same.jpg",
                    "thumbnail": "",
                    "width": 0,
                    "height": 0,
                    "source": "",
                },
            ],
            "next": None,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="v"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("test")

        assert len(resp.results) == 1


class TestDuckDuckGoVideosClient:
    """视频搜索客户端测试"""

    @pytest.fixture
    def client(self):
        return DuckDuckGoVideosClient()

    def test_engine_name(self, client):
        assert client.ENGINE_NAME == "duckduckgo_videos"

    @pytest.mark.asyncio
    async def test_search_no_vqd(self, client):
        with patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value=None):
            resp = await client.search("test")

        assert isinstance(resp, VideoSearchResponse)
        assert len(resp.results) == 0

    @pytest.mark.asyncio
    async def test_search_success(self, client):
        """正常视频搜索"""
        mock_json = {
            "results": [
                {
                    "title": "Python Tutorial",
                    "content": "https://youtube.com/watch?v=abc",
                    "duration": "10:30",
                    "publisher": "YouTube",
                    "published": "2024-01-15",
                    "description": "Learn Python",
                    "embed_url": "https://youtube.com/embed/abc",
                    "statistics": {"viewCount": 50000},
                    "images": {"large": "https://img.youtube.com/large.jpg"},
                },
            ],
            "next": None,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="vqd"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("python")

        assert len(resp.results) == 1
        r = resp.results[0]
        assert r.title == "Python Tutorial"
        assert r.url == "https://youtube.com/watch?v=abc"
        assert r.duration == "10:30"
        assert r.view_count == 50000
        assert r.thumbnail == "https://img.youtube.com/large.jpg"

    @pytest.mark.asyncio
    async def test_search_deduplicates_content_url(self, client):
        """相同视频 URL 去重"""
        mock_json = {
            "results": [
                {
                    "title": "V1",
                    "content": "https://same.com/v",
                    "duration": "",
                    "publisher": "",
                    "published": "",
                    "description": "",
                    "embed_url": "",
                    "statistics": {},
                    "images": {},
                },
                {
                    "title": "V2",
                    "content": "https://same.com/v",
                    "duration": "",
                    "publisher": "",
                    "published": "",
                    "description": "",
                    "embed_url": "",
                    "statistics": {},
                    "images": {},
                },
            ],
            "next": None,
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with (
            patch.object(client, "_get_vqd", new_callable=AsyncMock, return_value="v"),
            patch.object(client, "_fetch", new_callable=AsyncMock, return_value=mock_resp),
        ):
            resp = await client.search("test")

        assert len(resp.results) == 1
