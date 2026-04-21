"""Bilibili 客户端单元测试

Mock 策略：
    - 使用 BilibiliClient.__new__ 跳过 BaseScraper 真实 HTTP 客户端初始化
    - 预填充 WbiSigner 缓存，避免触发 /x/web-interface/nav 抓取
    - patch BilibiliClient._fetch (AsyncMock) 注入伪响应
    - _FakeResponse 提供 .json() 方法即可
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.models import SourceType, WebSearchResponse
from souwen.web.bilibili import BilibiliClient
from souwen.web.bilibili._errors import BilibiliNotFound
from souwen.web.bilibili.models import (
    BilibiliPopularVideo,
    BilibiliRankVideo,
    BilibiliUserInfo,
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
    # BaseScraper 内部属性占位
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
    # bilibili 自身属性
    client._sessdata = None
    client._bili_jct = None
    # 预填 WBI 缓存（避免触发 nav 抓取）
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
    """code != 0 时降级为空结果，不抛异常"""
    client = _build_client()
    payload = {"code": -412, "message": "rate limited", "data": {}}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        resp = await client.search("x")
    assert resp.results == []
    # error 路径下 numResults 缺失，total_results 退化为 0/len
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


# ─── get_user_info() ────────────────────────────────────────────────────


async def test_get_user_info_merges_endpoints():
    """get_user_info 调用三个接口，合并结果"""
    client = _build_client()

    info_payload = {
        "code": 0,
        "data": {
            "mid": 12345,
            "name": "测试用户",
            "face": "https://x/face.jpg",
            "sign": "签名",
            "level": 5,
            "sex": "男",
            "birthday": "01-01",
            "coins": 12.0,
            "vip": {"vip_type": 2, "vip_status": 1},
            "official": {"role": 1, "title": "官方", "desc": ""},
            "live_room": {"url": "https://live/1", "liveStatus": 1},
        },
    }
    stat_payload = {
        "code": 0,
        "data": {"following": 100, "follower": 5000},
    }
    nav_payload = {
        "code": 0,
        "data": {"video": 42},
    }

    # 三次顺序调用：acc/info → relation/stat → space/navnum
    fetch = AsyncMock(
        side_effect=[
            _resp(info_payload),
            _resp(stat_payload),
            _resp(nav_payload),
        ]
    )
    with patch.object(BilibiliClient, "_fetch", new=fetch):
        u = await client.get_user_info(12345)

    assert isinstance(u, BilibiliUserInfo)
    assert u.mid == 12345
    assert u.name == "测试用户"
    assert u.following == 100
    assert u.follower == 5000
    assert u.archive_count == 42
    assert u.vip.vip_type == 2
    assert u.live_status == 1
    assert u.live_room_url == "https://live/1"
    assert u.space_url == "https://space.bilibili.com/12345"
    assert fetch.await_count == 3


# ─── get_comments() ─────────────────────────────────────────────────────


async def test_get_comments_pagination():
    """跨多页累积评论，max_comments 截断"""
    client = _build_client()

    view_payload = {
        "code": 0,
        "data": {"bvid": "BV1xx", "aid": 999, "cid": 1},
    }

    def _make_replies(start: int, n: int):
        return [
            {
                "rpid": start + i,
                "mid": 1000 + i,
                "ctime": 1700000000,
                "like": i,
                "rcount": 0,
                "member": {"mid": 1000 + i, "uname": f"u{i}", "avatar": "", "level_info": {}},
                "content": {"message": f"msg-{start + i}"},
            }
            for i in range(n)
        ]

    page1 = {
        "code": 0,
        "data": {"replies": _make_replies(1, 20), "page": {"count": 50, "size": 20, "num": 1}},
    }
    page2 = {
        "code": 0,
        "data": {"replies": _make_replies(21, 20), "page": {"count": 50, "size": 20, "num": 2}},
    }
    page3 = {
        "code": 0,
        "data": {"replies": _make_replies(41, 10), "page": {"count": 50, "size": 20, "num": 3}},
    }

    fetch = AsyncMock(
        side_effect=[
            _resp(view_payload),
            _resp(page1),
            _resp(page2),
            _resp(page3),
        ]
    )
    with patch.object(BilibiliClient, "_fetch", new=fetch):
        comments = await client.get_comments("BV1xx", max_comments=25)

    # max_comments 截断到 25
    assert len(comments) == 25
    assert comments[0].text == "msg-1"
    assert comments[24].text == "msg-25"


# ─── get_popular() / get_ranking() — 软失败 ─────────────────────────────


async def test_get_popular_soft_fail():
    client = _build_client()
    payload = {"code": -412, "message": "rate", "data": None}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        items = await client.get_popular()
    assert items == []


async def test_get_popular_success():
    client = _build_client()
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "bvid": "BV1aa",
                    "aid": 1,
                    "title": "热门 1",
                    "pic": "",
                    "desc": "d",
                    "duration": 60,
                    "pubdate": 1700000000,
                    "owner": {"mid": 1, "name": "U"},
                    "stat": {"view": 100},
                    "rcmd_reason": {"content": "推荐理由"},
                }
            ]
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        items = await client.get_popular()
    assert len(items) == 1
    assert isinstance(items[0], BilibiliPopularVideo)
    assert items[0].rcmd_reason == "推荐理由"
    assert items[0].description == "d"


async def test_get_ranking_soft_fail():
    client = _build_client()
    payload = {"code": -352, "message": "risk", "data": None}
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        items = await client.get_ranking()
    assert items == []


async def test_get_ranking_success():
    client = _build_client()
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "bvid": "BV1aa",
                    "aid": 1,
                    "title": "rank1",
                    "pic": "",
                    "desc": "",
                    "duration": 60,
                    "pubdate": 1700000000,
                    "owner": {"mid": 1, "name": "U"},
                    "stat": {"view": 100},
                    "score": 9999,
                },
                {
                    "bvid": "BV1bb",
                    "aid": 2,
                    "title": "rank2",
                    "score": 8888,
                },
            ]
        },
    }
    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_resp(payload))):
        items = await client.get_ranking(rid=0, type="all")
    assert len(items) == 2
    assert isinstance(items[0], BilibiliRankVideo)
    assert items[0].rank_index == 1
    assert items[1].rank_index == 2
    assert items[0].score == 9999


# ─── _clean_html ────────────────────────────────────────────────────────


def test_clean_html():
    assert BilibiliClient._clean_html('<em class="keyword">x</em>') == "x"
    assert BilibiliClient._clean_html("<b>a</b><i>b</i>") == "ab"
    assert BilibiliClient._clean_html("  <em>x</em>  ") == "x"
    assert BilibiliClient._clean_html("") == ""
    assert BilibiliClient._clean_html(None) == ""  # type: ignore[arg-type]
    # 无 HTML 标签则保留原文
    assert BilibiliClient._clean_html("plain text") == "plain text"
