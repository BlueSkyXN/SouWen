"""Bilibili 客户端单元测试（精简版：搜索 + 抓取）

Mock 策略：
    - 使用 BilibiliClient.__new__ 跳过 BaseScraper 真实 HTTP 客户端初始化
    - 预填充 WbiSigner 缓存，避免触发 /x/web-interface/nav 抓取
    - patch BilibiliClient._fetch (AsyncMock) 注入伪响应
    - _FakeResponse 提供 .json() 方法即可
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from souwen.models import SourceType, WebSearchResponse
from souwen.web.bilibili import BilibiliClient
from souwen.web.bilibili._errors import BilibiliNotFound
from souwen.web.bilibili.models import (
    BilibiliArticleResult,
    BilibiliSearchUserItem,
    BilibiliVideoDetail,
)
from souwen.web.bilibili.wbi import WbiSigner


# ─── helpers ────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200
        self.text = ""
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


def _build_client() -> BilibiliClient:
    """构造一个跳过网络初始化、且 WBI 缓存已预填充的客户端"""
    client = BilibiliClient.__new__(BilibiliClient)
    client.min_delay = 0.0
    client.max_delay = 0.0
    client.max_retries = 1
    client._backoff_multiplier = 1.0
    client._fingerprint = None
    client._channel_headers = {}
    client._use_curl_cffi = False
    client._curl_session = None
    client._httpx_client = None
    client._resolved_base_url = BilibiliClient.BASE_URL
    client._sessdata = None
    client._bili_jct = None
    signer = WbiSigner()
    signer._img_key = "7cd084941338484aae1ad9425b84077c"
    signer._sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    signer._fetched_at = time.time()
    client._wbi = signer
    return client


def _resp(payload: dict) -> _FakeResponse:
    return _FakeResponse(payload)


# ─── search() ───────────────────────────────────────────────────────────


async def test_search_returns_web_search_response():
    client = _build_client()
    payload = {
        "code": 0,
        "message": "0",
        "data": {
            "result": [
                {
                    "title": "Python 入门",
                    "arcurl": "https://www.bilibili.com/video/BV1xx",
                    "description": "教程视频",
                    "author": "UP1",
                    "mid": 1,
                    "play": 100,
                    "video_review": 1,
                    "favorites": 0,
                    "duration": "1:23",
                    "pubdate": 1700000000,
                    "tag": "python",
                    "bvid": "BV1xx",
                    "aid": 1,
                }
            ],
            "numResults": 1,
            "numPages": 1,
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        resp = await client.search("python", max_results=5)

    assert isinstance(resp, WebSearchResponse)
    assert resp.query == "python"
    assert resp.source == SourceType.WEB_BILIBILI
    assert len(resp.results) == 1
    assert resp.results[0].title == "Python 入门"
    assert resp.results[0].engine == "bilibili"
    assert resp.results[0].raw["bvid"] == "BV1xx"


async def test_search_empty_on_error():
    client = _build_client()
    payload = {"code": -412, "message": "rate limited", "data": {}}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        resp = await client.search("x")
    assert resp.results == []
    assert resp.source == SourceType.WEB_BILIBILI


async def test_search_cleans_html_titles():
    client = _build_client()
    payload = {
        "code": 0,
        "data": {
            "result": [
                {
                    "title": '<em class="keyword">AI</em> <b>大模型</b>教程',
                    "arcurl": "https://www.bilibili.com/video/BV1aa",
                    "description": "",
                    "bvid": "BV1aa",
                }
            ],
            "numResults": 1,
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        resp = await client.search("ai")
    assert resp.results[0].title == "AI 大模型教程"


# ─── search_users() ─────────────────────────────────────────────────────


async def test_search_users_returns_items():
    client = _build_client()
    payload = {
        "code": 0,
        "data": {
            "result": [
                {
                    "mid": 100,
                    "uname": "测试 UP",
                    "usign": "签名",
                    "fans": 10000,
                    "videos": 50,
                    "level": 5,
                    "upic": "https://x/avatar.jpg",
                    "official_verify": {"type": 0},
                },
                {
                    "mid": 200,
                    "uname": "B",
                    "fans": 5,
                },
            ],
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        items = await client.search_users("kw", max_results=5)
    assert len(items) == 2
    assert isinstance(items[0], BilibiliSearchUserItem)
    assert items[0].mid == 100
    assert items[0].uname == "测试 UP"
    assert items[0].official_verify_type == 0
    assert items[0].space_url == "https://space.bilibili.com/100"


async def test_search_users_soft_fail():
    client = _build_client()
    payload = {"code": -412, "message": "rate", "data": None}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        items = await client.search_users("x")
    assert items == []


# ─── search_articles() ─────────────────────────────────────────────────


async def test_search_articles_success():
    client = _build_client()
    payload = {
        "code": 0,
        "data": {
            "result": [
                {
                    "id": 12345,
                    "title": '<em class="keyword">AI</em> 文章',
                    "author": "作者",
                    "mid": 999,
                    "category_name": "科技",
                    "desc": "摘要",
                    "view": 1000,
                    "like": 100,
                    "reply": 10,
                    "pub_date": 1700000000,
                    "image_urls": ["https://x/cover.jpg", ""],
                },
                {
                    "id": 67890,
                    "title": "另一篇",
                    "author": "作者2",
                },
            ],
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        results = await client.search_articles("ai", max_results=5)

    assert len(results) == 2
    assert isinstance(results[0], BilibiliArticleResult)
    assert results[0].id == 12345
    assert results[0].title == "AI 文章"
    assert results[0].author == "作者"
    assert results[0].category_name == "科技"
    assert results[0].view == 1000
    assert results[0].url == "https://www.bilibili.com/read/cv12345"
    assert results[0].image_urls == ["https://x/cover.jpg"]
    assert results[1].id == 67890
    assert results[1].view == 0
    assert results[1].url == "https://www.bilibili.com/read/cv67890"


async def test_search_articles_soft_fail():
    client = _build_client()
    payload = {"code": -412, "message": "rate", "data": None}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        results = await client.search_articles("x")
    assert results == []


async def test_search_articles_max_results_truncation():
    client = _build_client()
    raw_items = [{"id": i, "title": f"t{i}"} for i in range(1, 11)]
    payload = {"code": 0, "data": {"result": raw_items}}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        results = await client.search_articles("kw", max_results=3)
    assert len(results) == 3
    assert [r.id for r in results] == [1, 2, 3]


# ─── get_video_details() ────────────────────────────────────────────────


async def test_get_video_details_success():
    client = _build_client()
    payload = {
        "code": 0,
        "data": {
            "bvid": "BV1xx",
            "aid": 100,
            "cid": 200,
            "title": "示例标题",
            "desc": "描述",
            "pic": "https://x/pic.jpg",
            "duration": 125,
            "pubdate": 1700000000,
            "ctime": 1700000000,
            "owner": {"mid": 1, "name": "U", "face": "https://x/a.jpg"},
            "stat": {"view": 999, "like": 88, "coin": 7},
            "tname": "知识",
            "dynamic": "动态",
            "tags": [{"tag_name": "AI"}, {"tag_name": "教程"}],
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        v = await client.get_video_details("BV1xx")

    assert isinstance(v, BilibiliVideoDetail)
    assert v.bvid == "BV1xx"
    assert v.aid == 100
    assert v.cid == 200
    assert v.title == "示例标题"
    assert v.description == "描述"
    assert v.duration == 125
    assert v.duration_str == "2:05"
    assert v.owner.name == "U"
    assert v.stat.view == 999
    assert v.tags == ["AI", "教程"]
    assert v.url == "https://www.bilibili.com/video/BV1xx"


async def test_get_video_details_not_found():
    client = _build_client()
    payload = {"code": -404, "message": "啥都木有", "data": None}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        with pytest.raises(BilibiliNotFound) as exc:
            await client.get_video_details("BV1notfound")
    assert exc.value.code == -404


# ─── _clean_html ────────────────────────────────────────────────────────


def test_clean_html():
    assert BilibiliClient._clean_html('<em class="keyword">x</em>') == "x"
    assert BilibiliClient._clean_html("<b>a</b><i>b</i>") == "ab"
    assert BilibiliClient._clean_html("  <em>x</em>  ") == "x"
    assert BilibiliClient._clean_html("") == ""
    assert BilibiliClient._clean_html(None) == ""  # type: ignore[arg-type]
    assert BilibiliClient._clean_html("plain text") == "plain text"
