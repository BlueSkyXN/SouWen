"""知乎搜索客户端单元测试

文件用途：
    覆盖 souwen.web.zhihu.ZhihuClient 的核心行为：
    - 正常搜索：返回结果数量、字段映射正确
    - answer/question/article 三种 object.type 的字段映射
    - HTML 高亮标签清理：摘要中的 <em> 被去除
    - 空结果处理：data 为空时安全返回
    - snippet 截断：超长摘要被裁剪到 300 字符
    - max_results 上限截断到 20
    - HTTP / JSON 异常处理：降级为空结果

Mock 策略：
    BaseScraper._fetch 返回一个具有 .json() 方法的伪响应对象，
    避免真实 HTTP 调用；同时构造 ZhihuClient 时 stub 掉父类
    __init__，跳过 curl_cffi/httpx 客户端的实际创建。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from souwen.models import SourceType
from souwen.web.zhihu import ZhihuClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """伪 HTTP 响应：仅暴露 ZhihuClient 用到的接口"""

    def __init__(self, data, status_code: int = 200):
        self._data = data
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self):
        return self._data

    @property
    def text(self) -> str:
        return str(self._data)


def _build_client() -> ZhihuClient:
    """构造一个跳过网络初始化的 ZhihuClient"""
    client = ZhihuClient.__new__(ZhihuClient)
    client.min_delay = 0.0
    client.max_delay = 0.0
    client.max_retries = 1
    client._backoff_multiplier = 1.0
    client._fingerprint = None
    client._channel_headers = {}
    client._use_curl_cffi = False
    client._curl_session = None
    client._httpx_client = None
    client._resolved_base_url = ZhihuClient.BASE_URL
    return client


def _answer_item(**overrides) -> dict:
    obj = {
        "type": "answer",
        "id": 100001,
        "url": "https://www.zhihu.com/question/123/answer/456",
        "excerpt": "这是一个 <em>Python</em> 回答的摘要内容",
        "author": {"name": "张三"},
        "voteup_count": 888,
        "question": {
            "id": 123,
            "title": "如何学习 <em>Python</em>?",
        },
    }
    obj.update(overrides)
    return {"type": "search_result", "object": obj}


def _question_item(**overrides) -> dict:
    obj = {
        "type": "question",
        "id": 222,
        "title": "什么是 <em>机器学习</em>?",
        "excerpt": "机器学习的简介摘要",
        "author": {"name": "李四"},
    }
    obj.update(overrides)
    return {"type": "search_result", "object": obj}


def _article_item(**overrides) -> dict:
    obj = {
        "type": "article",
        "id": 333,
        "title": "<em>深度学习</em>入门指南",
        "url": "https://zhuanlan.zhihu.com/p/333",
        "excerpt": "深度学习入门指南摘要",
        "author": {"name": "王五"},
        "voteup_count": 100,
    }
    obj.update(overrides)
    return {"type": "search_result", "object": obj}


def _payload(items: list[dict] | None = None, totals: int = 100) -> dict:
    return {
        "data": items if items is not None else [],
        "paging": {"totals": totals, "is_end": False},
    }


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


def test_zhihu_source_type_exists():
    assert SourceType.WEB_ZHIHU.value == "web_zhihu"


# ---------------------------------------------------------------------------
# _clean_html
# ---------------------------------------------------------------------------


def test_html_cleanup():
    assert ZhihuClient._clean_html("<em>Python</em> 教程") == "Python 教程"
    assert ZhihuClient._clean_html("<b>x</b><i>y</i>") == "xy"
    assert ZhihuClient._clean_html("  <em>x</em>  ") == "x"
    assert ZhihuClient._clean_html("") == ""
    assert ZhihuClient._clean_html(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# search() 正常路径
# ---------------------------------------------------------------------------


def test_basic_search():
    client = _build_client()
    fake = _FakeResponse(_payload(items=[_answer_item(), _article_item()]))

    with patch.object(
        ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)
    ) as mocked:
        resp = _run(client.search("python", max_results=10))

    assert mocked.await_count == 1
    call = mocked.await_args
    url = call.args[0]
    assert "/api/v4/search_v3" in url
    assert "t=general" in url
    assert "q=python" in url
    assert "limit=10" in url
    assert "correction=1" in url
    assert "offset=0" in url

    headers = call.kwargs["headers"]
    assert headers["Referer"] == "https://www.zhihu.com/search"
    assert headers["x-requested-with"] == "fetch"
    assert "application/json" in headers["Accept"]

    assert resp.query == "python"
    assert resp.source == SourceType.WEB_ZHIHU
    assert len(resp.results) == 2
    assert resp.total_results == 100


def test_answer_type():
    client = _build_client()
    fake = _FakeResponse(_payload(items=[_answer_item()]))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("python"))

    assert len(resp.results) == 1
    r = resp.results[0]
    # title 来自 question.title，并清理 HTML
    assert r.title == "如何学习 Python?"
    assert r.url == "https://www.zhihu.com/question/123/answer/456"
    assert r.snippet == "这是一个 Python 回答的摘要内容"
    assert r.engine == "zhihu"
    assert r.source == SourceType.WEB_ZHIHU
    assert r.raw["type"] == "answer"
    assert r.raw["id"] == 100001
    assert r.raw["author"] == "张三"
    assert r.raw["voteup_count"] == 888


def test_question_type():
    client = _build_client()
    # 不提供 url，验证回退到 https://www.zhihu.com/question/{id}
    fake = _FakeResponse(_payload(items=[_question_item()]))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("ml"))

    assert len(resp.results) == 1
    r = resp.results[0]
    assert r.title == "什么是 机器学习?"
    assert r.url == "https://www.zhihu.com/question/222"
    assert r.snippet == "机器学习的简介摘要"
    assert r.raw["type"] == "question"
    assert r.raw["id"] == 222


def test_article_type():
    client = _build_client()
    fake = _FakeResponse(_payload(items=[_article_item()]))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("dl"))

    assert len(resp.results) == 1
    r = resp.results[0]
    assert r.title == "深度学习入门指南"
    assert r.url == "https://zhuanlan.zhihu.com/p/333"
    assert r.snippet == "深度学习入门指南摘要"
    assert r.raw["type"] == "article"
    assert r.raw["id"] == 333
    assert r.raw["author"] == "王五"


def test_empty_results():
    client = _build_client()
    fake = _FakeResponse(_payload(items=[], totals=0))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("nothing"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_ZHIHU


def test_snippet_truncation():
    client = _build_client()
    long_excerpt = "x" * 1000
    fake = _FakeResponse(_payload(items=[_article_item(excerpt=long_excerpt)]))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("x"))

    assert len(resp.results[0].snippet) == 300
    assert resp.results[0].snippet == "x" * 300


def test_max_results_capped():
    """max_results 超过 20 时，URL 中的 limit 被截断到 20"""
    client = _build_client()
    fake = _FakeResponse(_payload(items=[]))

    with patch.object(
        ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)
    ) as mocked:
        _run(client.search("x", max_results=999))

    assert "limit=20" in mocked.await_args.args[0]


def test_max_results_limits_returned_count():
    """返回结果数量受 max_results 限制"""
    client = _build_client()
    items = [_article_item(id=i, url=f"https://zhuanlan.zhihu.com/p/{i}") for i in range(10)]
    fake = _FakeResponse(_payload(items=items))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("x", max_results=3))

    assert len(resp.results) == 3


def test_skips_invalid_items():
    """缺少 title/url 或 object 非 dict 的条目应被跳过"""
    client = _build_client()
    items = [
        _article_item(),
        {"type": "search_result", "object": {"type": "article", "title": "no url"}},
        {"type": "search_result", "object": "not-a-dict"},
        "string-not-dict",
        {"type": "search_result"},  # 缺少 object
    ]
    fake = _FakeResponse(_payload(items=items))

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("x"))

    assert len(resp.results) == 1
    assert resp.results[0].raw["type"] == "article"


# ---------------------------------------------------------------------------
# 异常 / 降级
# ---------------------------------------------------------------------------


def test_error_handling_fetch_exception():
    client = _build_client()

    with patch.object(
        ZhihuClient, "_fetch", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0
    assert resp.source == SourceType.WEB_ZHIHU


def test_error_handling_invalid_json():
    client = _build_client()

    class _BadResp:
        status_code = 200
        text = "not json"
        headers: dict = {}

        def json(self):
            raise ValueError("invalid json")

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=_BadResp())):
        resp = _run(client.search("x"))

    assert resp.results == []
    assert resp.total_results == 0


def test_error_handling_non_list_data():
    client = _build_client()
    fake = _FakeResponse({"data": {"unexpected": "shape"}, "paging": {}})

    with patch.object(ZhihuClient, "_fetch", new=AsyncMock(return_value=fake)):
        resp = _run(client.search("x"))

    assert resp.results == []
