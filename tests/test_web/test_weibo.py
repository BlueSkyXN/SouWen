"""微博搜索客户端单元测试

文件用途：
    覆盖 souwen.web.weibo.WeiboClient 的核心行为：
    - 正常搜索：返回结果数量、字段映射正确
    - 空结果处理：data.cards 为空时安全返回
    - 跳过非微博卡片：card_type != 9 的卡片被忽略
    - HTML 标签清理：<p>、<br>、<a> 等被去除
    - 长文本截断：snippet 300 / title 100
    - max_results 限制
    - 异常处理：_fetch 抛错、JSON 解析失败
    - ok 字段校验：data.ok != 1 时降级为空结果
    - raw 字段中包含用户信息

Mock 策略：
    BaseScraper._fetch 返回一个具有 .json() 方法的伪响应对象，
    避免真实 HTTP 调用；同时构造 WeiboClient 时跳过父类 __init__，
    避免 curl_cffi/httpx 客户端的实际创建。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from souwen.models import SourceType
from souwen.web.weibo import WeiboClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """伪 HTTP 响应：仅暴露 WeiboClient 用到的接口"""

    def __init__(self, data: dict, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._data

    @property
    def text(self) -> str:
        return str(self._data)


def _build_client() -> WeiboClient:
    """构造一个跳过网络初始化的 WeiboClient"""
    client = WeiboClient.__new__(WeiboClient)
    client.min_delay = 0.0
    client.max_delay = 0.0
    client.max_retries = 1
    client._backoff_multiplier = 1.0
    client._fingerprint = None
    client._channel_headers = {}
    client._use_curl_cffi = False
    client._curl_session = None
    client._httpx_client = None
    client._resolved_base_url = WeiboClient.BASE_URL
    return client


def _mblog_card(**overrides) -> dict:
    mblog = {
        "id": "4567890123",
        "bid": "Lxxxxxxxx",
        "text": "<p>这是一条<a href='/n/foo'>@用户</a>的微博正文</p>",
        "user": {"screen_name": "测试用户A", "id": 11111},
        "created_at": "Mon Jan 01 12:00:00 +0800 2024",
        "reposts_count": 10,
        "comments_count": 20,
        "attitudes_count": 30,
    }
    mblog.update(overrides)
    return {"card_type": 9, "mblog": mblog}


def _payload(cards: list[dict] | None = None, ok: int = 1) -> dict:
    return {
        "ok": ok,
        "data": {
            "cards": cards if cards is not None else [],
        },
    }


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 枚举扩展
# ---------------------------------------------------------------------------


def test_weibo_source_type_exists():
    assert SourceType.WEB_WEIBO.value == "web_weibo"


# ---------------------------------------------------------------------------
# _clean_html
# ---------------------------------------------------------------------------


def test_clean_html_strips_tags():
    text = "<p>hello <a href='x'>world</a></p>"
    assert WeiboClient._clean_html(text) == "hello world"


def test_clean_html_replaces_br_with_space():
    text = "line1<br />line2<br/>line3"
    assert WeiboClient._clean_html(text) == "line1 line2 line3"


def test_clean_html_collapses_whitespace():
    text = "  <p>a   b\n\nc</p>  "
    assert WeiboClient._clean_html(text) == "a b c"


def test_clean_html_handles_empty():
    assert WeiboClient._clean_html("") == ""
    assert WeiboClient._clean_html(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# search() — 正常路径
# ---------------------------------------------------------------------------


def test_basic_search():
    client = _build_client()
    cards = [_mblog_card(), _mblog_card(id="9999", text="<p>第二条</p>")]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)) as mocked:
        resp = _run(client.search("python", max_results=10))

    assert mocked.await_count == 1
    call = mocked.await_args
    url = call.args[0]
    assert "containerid=100103type%3D1%26q%3Dpython" in url
    assert "page_type=searchall" in url
    headers = call.kwargs["headers"]
    assert headers["Referer"] == "https://m.weibo.cn/search"
    assert headers["X-Requested-With"] == "XMLHttpRequest"

    assert resp.query == "python"
    assert resp.source == SourceType.WEB_WEIBO
    assert len(resp.results) == 2
    assert resp.total_results == 2

    first = resp.results[0]
    assert first.title == "这是一条@用户的微博正文"
    assert first.url == "https://m.weibo.cn/detail/4567890123"
    assert first.snippet == "这是一条@用户的微博正文"
    assert first.engine == "weibo"
    assert first.source == SourceType.WEB_WEIBO


def test_empty_cards():
    client = _build_client()
    fake_resp = _FakeResponse(_payload(cards=[]))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("nothing"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_WEIBO


def test_skip_non_mblog_cards():
    client = _build_client()
    cards = [
        {"card_type": 11, "card_group": [{"foo": "bar"}]},  # 话题卡
        _mblog_card(),
        {"card_type": 7, "title_sub": {"text": "猜你想搜"}},
        _mblog_card(id="222", text="<p>第二条</p>"),
        {"card_type": 9, "mblog": "not-a-dict"},  # mblog 字段非法
        "not-a-dict",  # 卡片本身非 dict
    ]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert len(resp.results) == 2
    assert resp.results[0].url == "https://m.weibo.cn/detail/4567890123"
    assert resp.results[1].url == "https://m.weibo.cn/detail/222"


def test_html_cleanup():
    client = _build_client()
    raw_text = (
        "<p>第一行<br />第二行<br/>第三行"
        "<a href='/n/abc' data-hide=''>@张三</a>"
        "<span class='url-icon'><img src='x' /></span>"
        "正文结尾</p>"
    )
    cards = [_mblog_card(text=raw_text)]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert resp.results[0].snippet == "第一行 第二行 第三行@张三正文结尾"
    assert "<" not in resp.results[0].snippet
    assert ">" not in resp.results[0].snippet


def test_snippet_truncation():
    client = _build_client()
    long_text = "<p>" + ("啊" * 1000) + "</p>"
    cards = [_mblog_card(text=long_text)]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert len(resp.results[0].snippet) == 300
    assert resp.results[0].snippet == "啊" * 300


def test_title_truncation():
    client = _build_client()
    long_text = "<p>" + ("a" * 500) + "</p>"
    cards = [_mblog_card(text=long_text)]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert len(resp.results[0].title) == 100
    assert resp.results[0].title == "a" * 100


def test_max_results_limit():
    client = _build_client()
    cards = [_mblog_card(id=str(i), text=f"<p>条目{i}</p>") for i in range(10)]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x", max_results=3))

    assert len(resp.results) == 3
    assert resp.total_results == 3


# ---------------------------------------------------------------------------
# search() — 异常路径
# ---------------------------------------------------------------------------


def test_error_handling_fetch_exception():
    client = _build_client()

    with patch.object(
        WeiboClient, "_fetch", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_WEIBO


def test_error_handling_invalid_json():
    client = _build_client()

    class _BadResp:
        status_code = 200
        text = "not json"
        headers: dict = {}

        def json(self):
            raise ValueError("invalid json")

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=_BadResp())):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0


def test_ok_field_check():
    client = _build_client()
    fake_resp = _FakeResponse({"ok": 0, "msg": "限流", "data": {"cards": []}})

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_WEIBO


def test_user_info_in_raw():
    client = _build_client()
    cards = [_mblog_card()]
    fake_resp = _FakeResponse(_payload(cards=cards))

    with patch.object(WeiboClient, "_fetch", new=AsyncMock(return_value=fake_resp)):
        resp = _run(client.search("x"))

    raw = resp.results[0].raw
    assert raw["user"] == "测试用户A"
    assert raw["reposts_count"] == 10
    assert raw["comments_count"] == 20
    assert raw["attitudes_count"] == 30
    assert raw["created_at"] == "Mon Jan 01 12:00:00 +0800 2024"
    assert raw["bid"] == "Lxxxxxxxx"
    assert raw["mid"] == "4567890123"
