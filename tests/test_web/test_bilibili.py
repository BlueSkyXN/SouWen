"""Bilibili 搜索客户端单元测试

文件用途：
    覆盖 souwen.web.bilibili.BilibiliClient 的核心行为：
    - 正常搜索：返回结果数量、字段映射正确
    - HTML 高亮标签清理：title 中的 <em class="keyword"> 被去除
    - 空结果处理：data.result 为空时安全返回
    - description 截断：超长 snippet 被裁剪到 300 字符
    - API 错误码处理：code != 0 时降级为空结果
    - HTTP 异常处理：_fetch 抛出异常时降级为空结果
    - 排序参数透传：order 参数被拼接到 URL
    - _clean_html 静态方法的边界值

Mock 策略：
    BaseScraper._fetch 返回一个具有 .json() 方法的伪响应对象，
    避免真实 HTTP 调用；同时构造 BilibiliClient 时 stub 掉父类
    __init__，跳过 curl_cffi/httpx 客户端的实际创建。
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from souwen.web.bilibili import BilibiliClient
from souwen.web.bilibili.wbi import WbiSigner
from souwen.models import SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """伪 HTTP 响应：仅暴露 BilibiliClient 用到的接口"""

    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


def _build_client() -> BilibiliClient:
    """构造一个跳过网络初始化的 BilibiliClient"""
    client = BilibiliClient.__new__(BilibiliClient)
    # 复刻 BaseScraper 中 _fetch / search 会读取的属性
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
    # 预填 WBI 缓存，避免触发 nav 抓取
    signer = WbiSigner()
    signer._img_key = "7cd084941338484aae1ad9425b84077c"
    signer._sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    signer._fetched_at = time.time()
    client._wbi = signer
    return client


def _sample_payload(items: list[dict] | None = None, num_results: int = 100) -> dict:
    return {
        "code": 0,
        "message": "0",
        "data": {
            "result": items if items is not None else [],
            "numResults": num_results,
            "numPages": 5,
        },
    }


def _sample_item(**overrides) -> dict:
    base = {
        "title": '<em class="keyword">Python</em> 入门教程',
        "arcurl": "https://www.bilibili.com/video/BV1xx411c7mD",
        "description": "这是一个 Python 入门教程视频",
        "author": "UP主A",
        "mid": 12345678,
        "play": 99999,
        "video_review": 100,
        "favorites": 50,
        "duration": "12:34",
        "pubdate": 1609459200,
        "tag": "python,教程,编程",
        "bvid": "BV1xx411c7mD",
        "aid": 999,
    }
    base.update(overrides)
    return base


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# 枚举扩展
# ---------------------------------------------------------------------------


def test_bilibili_source_type_exists():
    """SourceType.WEB_BILIBILI 枚举值应已注册"""
    assert SourceType.WEB_BILIBILI.value == "web_bilibili"


# ---------------------------------------------------------------------------
# _clean_html
# ---------------------------------------------------------------------------


def test_clean_html_strips_em_tags():
    text = '<em class="keyword">Python</em> 教程'
    assert BilibiliClient._clean_html(text) == "Python 教程"


def test_clean_html_strips_multiple_tags():
    text = "<b>hello</b> <i>world</i>"
    assert BilibiliClient._clean_html(text) == "hello world"


def test_clean_html_handles_empty():
    assert BilibiliClient._clean_html("") == ""
    assert BilibiliClient._clean_html(None) == ""  # type: ignore[arg-type]


def test_clean_html_strips_whitespace():
    assert BilibiliClient._clean_html("  <em>x</em>  ") == "x"


# ---------------------------------------------------------------------------
# search() — 正常路径
# ---------------------------------------------------------------------------


def test_search_returns_results():
    client = _build_client()
    payload = _sample_payload(
        items=[_sample_item(), _sample_item(arcurl="https://www.bilibili.com/video/BV2")]
    )
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        resp = _run(client.search("python", max_results=10))

    assert mocked.await_count == 1
    # 校验 URL 与必备 headers
    call_args = mocked.await_args
    assert "search_type=video" in call_args.args[0]
    assert "keyword=python" in call_args.args[0]
    assert "order=totalrank" in call_args.args[0]
    assert call_args.kwargs["headers"]["Referer"] == "https://www.bilibili.com"

    assert resp.query == "python"
    assert resp.source == SourceType.WEB_BILIBILI
    assert len(resp.results) == 2
    assert resp.total_results == 100

    first = resp.results[0]
    assert first.title == "Python 入门教程"  # <em> 被清理
    assert first.url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert first.snippet == "这是一个 Python 入门教程视频"
    assert first.engine == "bilibili"
    assert first.raw["author"] == "UP主A"
    assert first.raw["play"] == 99999
    assert first.raw["bvid"] == "BV1xx411c7mD"


def test_search_html_tag_cleaning_in_results():
    client = _build_client()
    payload = _sample_payload(
        items=[_sample_item(title='<em class="keyword">AI</em> <b>大模型</b>')]
    )
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("ai"))

    assert resp.results[0].title == "AI 大模型"


def test_search_empty_results():
    client = _build_client()
    fake_resp = _FakeResponse(_sample_payload(items=[], num_results=0))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("nonexistent"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_BILIBILI


def test_search_truncates_description():
    client = _build_client()
    long_desc = "a" * 1000
    payload = _sample_payload(items=[_sample_item(description=long_desc)])
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert len(resp.results[0].snippet) == 300
    assert resp.results[0].snippet == "a" * 300


def test_search_respects_max_results():
    client = _build_client()
    items = [_sample_item(arcurl=f"https://www.bilibili.com/video/BV{i}") for i in range(10)]
    fake_resp = _FakeResponse(_sample_payload(items=items))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x", max_results=3))

    assert len(resp.results) == 3


def test_search_skips_items_missing_title_or_url():
    client = _build_client()
    items = [
        _sample_item(),
        _sample_item(title="", arcurl="https://www.bilibili.com/video/BVno-title"),
        _sample_item(title="ok", arcurl=""),
        {"not": "a-dict"},  # 非 dict 应被跳过
    ]
    # items 列表里包含一个非 dict 元素
    raw_items: list = list(items)
    raw_items.append("string-not-dict")  # type: ignore[arg-type]
    fake_resp = _FakeResponse(_sample_payload(items=raw_items))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    # 只有第一个 _sample_item() 是合法完整的
    assert len(resp.results) == 1
    assert resp.results[0].title == "Python 入门教程"


# ---------------------------------------------------------------------------
# search() — 异常 / 降级路径
# ---------------------------------------------------------------------------


def test_search_handles_api_error_code():
    client = _build_client()
    fake_resp = _FakeResponse({"code": -412, "message": "请求被拦截", "data": None})

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0


def test_search_handles_fetch_exception():
    client = _build_client()

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(side_effect=RuntimeError("boom"))):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_BILIBILI


def test_search_handles_invalid_json():
    client = _build_client()

    class _BadResp:
        status_code = 200
        text = "not json"
        headers: dict = {}

        def json(self):
            raise ValueError("invalid json")

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=_BadResp())):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0


def test_search_handles_non_list_result_field():
    """/search/all/v2 端点的 data.result 是分组数组（dict 列表），但若返回非列表也要兜底"""
    client = _build_client()
    payload = {"code": 0, "data": {"result": {"unexpected": "shape"}, "numResults": 0}}
    fake_resp = _FakeResponse(payload)

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert resp.results == []


# ---------------------------------------------------------------------------
# search() — 排序参数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", ["totalrank", "click", "pubdate", "dm", "stow"])
def test_search_passes_order_param(order):
    client = _build_client()
    fake_resp = _FakeResponse(_sample_payload(items=[]))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        _run(client.search("x", order=order))

    assert f"order={order}" in mocked.await_args.args[0]


def test_search_clamps_max_results_to_50():
    client = _build_client()
    fake_resp = _FakeResponse(_sample_payload(items=[]))

    with patch.object(BilibiliClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        _run(client.search("x", max_results=999))

    assert "page_size=50" in mocked.await_args.args[0]
