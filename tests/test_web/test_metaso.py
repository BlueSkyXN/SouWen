"""Metaso 搜索客户端单元测试。

覆盖 ``souwen.web.metaso.MetasoClient`` 搜索和内容提取路径。使用 ``pytest-httpx``
直接 mock HTTP 层。

测试清单：
- ``test_init_without_api_key_raises``：未提供 API Key 时抛出 ConfigError
- ``test_init_with_api_key``：传入 API Key 后正确初始化
- ``test_search_document_scope``：document 范围搜索返回正确结果
- ``test_search_webpage_scope``：webpage 范围搜索返回正确结果
- ``test_search_scholar_scope``：scholar 范围搜索返回正确结果
- ``test_search_with_summary``：includeSummary 参数正确传递
- ``test_search_with_raw_content``：includeRawContent 参数正确传递
- ``test_search_empty_results``：空结果不崩溃
- ``test_search_skips_invalid_items``：缺少必填字段的条目被跳过
- ``test_search_invalid_json_raises_parse_error``：非 JSON 响应抛 ParseError
- ``test_reader_success``：Reader API 成功提取内容
- ``test_reader_error``：Reader API 失败时返回错误
"""

from __future__ import annotations

import pytest

from souwen.core.exceptions import ConfigError, ParseError  # noqa: E402
from souwen.web.metaso import MetasoClient  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _sample_search_response(items: list[dict] | None = None) -> dict:
    """构造 Metaso /search 风格的响应"""
    items = items if items is not None else []
    return {"data": items, "status": "success"}


def _sample_search_item(
    title: str = "示例标题",
    url: str = "https://example.com/page",
    snippet: str = "这是一个示例摘要",
    summary: str | None = None,
    raw_content: str | None = None,
    published_date: str | None = None,
    author: str | None = None,
    source: str | None = None,
) -> dict:
    """构造一条 Metaso 搜索结果 item"""
    item: dict = {
        "title": title,
        "url": url,
        "snippet": snippet,
    }
    if summary:
        item["summary"] = summary
    if raw_content:
        item["rawContent"] = raw_content
    if published_date:
        item["publishedDate"] = published_date
    if author:
        item["author"] = author
    if source:
        item["source"] = source
    return item


# ---------------------------------------------------------------------------
# __init__ tests
# ---------------------------------------------------------------------------


async def test_init_without_api_key_raises(monkeypatch):
    """未提供 API Key 时抛出 ConfigError"""
    monkeypatch.delenv("SOUWEN_METASO_API_KEY", raising=False)
    with pytest.raises(ConfigError) as exc_info:
        MetasoClient()
    assert "metaso_api_key" in str(exc_info.value)


async def test_init_with_api_key():
    """传入 API Key 时正确初始化"""
    async with MetasoClient(api_key="mk-test123") as client:
        assert client.api_key == "mk-test123"


# ---------------------------------------------------------------------------
# search tests
# ---------------------------------------------------------------------------


async def test_search_document_scope(httpx_mock):
    """document 范围搜索返回正确结果"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(
            items=[
                _sample_search_item(
                    title="AI 研究论文",
                    url="https://example.com/doc1",
                    snippet="关于 AI 的深度研究文档",
                    source="学术期刊",
                )
            ]
        ),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("AI", scope="document", max_results=10)

    assert resp.query == "AI"
    assert resp.source == "metaso"
    assert len(resp.results) == 1

    first = resp.results[0]
    assert first.title == "AI 研究论文"
    assert first.url == "https://example.com/doc1"
    assert first.snippet == "关于 AI 的深度研究文档"
    assert first.engine == "metaso"
    assert first.source == "metaso"
    assert first.raw["source_name"] == "学术期刊"

    # 验证请求参数
    req = httpx_mock.get_requests()[0]
    assert req.headers.get("authorization") == "Bearer mk-test"
    import json

    payload = json.loads(req.content)
    assert payload["q"] == "AI"
    assert payload["scope"] == "document"
    assert payload["size"] == 10


async def test_search_webpage_scope(httpx_mock):
    """webpage 范围搜索返回正确结果"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(
            items=[
                _sample_search_item(
                    title="AI 技术博客",
                    url="https://blog.example.com/ai",
                    snippet="最新 AI 技术分析",
                    published_date="2024-01-15",
                    author="张三",
                )
            ]
        ),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("AI", scope="webpage", max_results=20)

    assert len(resp.results) == 1
    first = resp.results[0]
    assert first.raw["published_date"] == "2024-01-15"
    assert first.raw["author"] == "张三"


async def test_search_scholar_scope(httpx_mock):
    """scholar 范围搜索返回正确结果"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(
            items=[
                _sample_search_item(
                    title="机器学习算法研究",
                    url="https://scholar.example.com/paper1",
                    snippet="深度学习算法创新研究",
                )
            ]
        ),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("机器学习", scope="scholar", max_results=5)

    assert len(resp.results) == 1
    # 验证请求参数
    req = httpx_mock.get_requests()[0]
    import json

    payload = json.loads(req.content)
    assert payload["scope"] == "scholar"
    assert payload["size"] == 5


async def test_search_with_summary(httpx_mock):
    """includeSummary 参数正确传递"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(
            items=[
                _sample_search_item(
                    title="测试",
                    url="https://test.com",
                    snippet="摘要",
                    summary="这是详细摘要内容",
                )
            ]
        ),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("test", include_summary=True)

    assert resp.results[0].raw["summary"] == "这是详细摘要内容"

    # 验证请求参数
    req = httpx_mock.get_requests()[0]
    import json

    payload = json.loads(req.content)
    assert payload["includeSummary"] is True


async def test_search_with_raw_content(httpx_mock):
    """includeRawContent 参数正确传递（仅 webpage 范围）"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(
            items=[
                _sample_search_item(
                    title="测试",
                    url="https://test.com",
                    snippet="摘要",
                    raw_content="完整的网页原始内容",
                )
            ]
        ),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("test", scope="webpage", include_raw_content=True)

    assert resp.results[0].raw["raw_content"] == "完整的网页原始内容"

    # 验证请求参数
    req = httpx_mock.get_requests()[0]
    import json

    payload = json.loads(req.content)
    assert payload["includeRawContent"] is True


async def test_search_empty_results(httpx_mock):
    """空结果不崩溃"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(items=[]),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("无结果查询")

    assert resp.results == []
    assert resp.total_results == 0


async def test_search_skips_invalid_items(httpx_mock):
    """缺少 title 或 url 的条目被跳过"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(
            items=[
                {"title": "", "url": "https://example.com", "snippet": "空标题"},  # 空标题
                {"title": "有效标题", "url": "", "snippet": "空 URL"},  # 空 URL
                _sample_search_item(title="正常条目", url="https://ok.com"),  # 有效
            ]
        ),
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.search("mixed")

    assert len(resp.results) == 1
    assert resp.results[0].title == "正常条目"


async def test_search_invalid_json_raises_parse_error(httpx_mock):
    """非 JSON 响应抛 ParseError"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        content=b"<html>not json</html>",
        headers={"Content-Type": "text/html"},
    )

    async with MetasoClient(api_key="mk-test") as client:
        with pytest.raises(ParseError):
            await client.search("bad")


async def test_search_max_results_capped_at_100(httpx_mock):
    """max_results 最大值限制为 100"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/search",
        json=_sample_search_response(items=[]),
    )

    async with MetasoClient(api_key="mk-test") as client:
        await client.search("test", max_results=200)

    # 验证实际请求的 size 参数
    req = httpx_mock.get_requests()[0]
    import json

    payload = json.loads(req.content)
    assert payload["size"] == 100  # 应该被限制为 100


# ---------------------------------------------------------------------------
# reader tests
# ---------------------------------------------------------------------------


async def test_reader_success(httpx_mock):
    """Reader API 成功提取内容"""
    httpx_mock.add_response(
        url="https://metaso.cn/api/v1/reader",
        content="这是从网页提取的纯文本内容。\n包含多行文字。".encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.reader("https://example.com/article")

    assert resp.total == 1
    assert resp.total_ok == 1
    assert resp.total_failed == 0
    assert resp.provider == "metaso"
    assert len(resp.results) == 1

    result = resp.results[0]
    assert result.url == "https://example.com/article"
    assert result.error is None
    assert result.content == "这是从网页提取的纯文本内容。\n包含多行文字。"
    assert result.content_format == "text"
    assert result.source == "metaso"
    assert result.snippet.startswith("这是从网页")

    # 验证请求
    req = httpx_mock.get_requests()[0]
    assert req.headers.get("authorization") == "Bearer mk-test"
    assert req.headers.get("accept") == "text/plain"
    import json

    payload = json.loads(req.content)
    assert payload["url"] == "https://example.com/article"


async def test_reader_error(httpx_mock):
    """Reader API 失败时返回错误"""
    import httpx

    httpx_mock.add_exception(httpx.ReadError("Network timeout"))

    async with MetasoClient(api_key="mk-test") as client:
        resp = await client.reader("https://example.com/fail")

    assert resp.total == 1
    assert resp.total_ok == 0
    assert resp.total_failed == 1
    assert len(resp.results) == 1

    result = resp.results[0]
    assert result.url == "https://example.com/fail"
    assert result.error is not None
    assert "Network timeout" in result.error
    assert result.source == "metaso"
