"""arXiv 全文获取客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.providers.runtime_clients.paper.arxiv_fulltext`` 中 ArxivFulltextClient 的 HTML 提取和
错误处理逻辑。无真实网络调用。

测试清单：
- ``test_html_success``：HTML 200 时提取标题与正文
- ``test_html_strips_unwanted_tags``：剥离 nav/script/style 等噪音
- ``test_html_not_found``：HTML 404 时返回错误
- ``test_html_request_failure``：HTML 请求异常时返回错误
- ``test_html_parse_failure``：HTML 解析异常时返回准确错误
"""

from __future__ import annotations

import re

from pytest_httpx import HTTPXMock

from souwen.providers.runtime_clients.paper.arxiv_fulltext import ArxivFulltextClient


HTML_PAGE = """\
<html>
<head><title>Sample arXiv Paper</title></head>
<body>
  <nav>navigation links</nav>
  <header>top header</header>
  <script>var x = 1;</script>
  <style>body{color:red;}</style>
  <main>
    <h1>Sample Title</h1>
    <p>This is the abstract.</p>
    <p>And this is the body content.</p>
  </main>
  <footer>copyright footer</footer>
</body>
</html>
"""


async def test_html_success(httpx_mock: HTTPXMock):
    """HTML 200 时返回 text 类型 FetchResult。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        text=HTML_PAGE,
    )

    async with ArxivFulltextClient() as c:
        result = await c.get_fulltext("2301.00001")

    assert result.error is None
    assert result.source == "arxiv_fulltext"
    assert result.content_format == "text"
    assert result.title == "Sample arXiv Paper"
    assert "Sample Title" in result.content
    assert "abstract" in result.content
    assert result.snippet  # 非空
    assert result.url == "https://arxiv.org/abs/2301.00001"
    assert result.raw["variant"] == "html"


async def test_html_strips_unwanted_tags(httpx_mock: HTTPXMock):
    """nav/header/footer/script/style 应当被完全移除。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        text=HTML_PAGE,
    )

    async with ArxivFulltextClient() as c:
        result = await c.get_fulltext("2301.00001")

    text = result.content
    assert "navigation links" not in text
    assert "top header" not in text
    assert "copyright footer" not in text
    assert "var x = 1" not in text
    assert "color:red" not in text


async def test_html_not_found(httpx_mock: HTTPXMock):
    """HTML 404 时返回可审计错误，不回退到 PDF。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        status_code=404,
        text="not found",
    )

    async with ArxivFulltextClient() as c:
        result = await c.get_fulltext("2301.99999")

    assert result.error is not None
    assert "404" in result.error
    assert result.content == ""


async def test_html_request_failure(httpx_mock: HTTPXMock):
    """HTML 请求异常时返回可审计错误。"""
    httpx_mock.add_exception(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        exception=TimeoutError("upstream timeout"),
    )

    async with ArxivFulltextClient() as c:
        result = await c.get_fulltext("2301.99999")

    assert result.error is not None
    assert "HTML 请求失败" in result.error


async def test_html_parse_failure(httpx_mock: HTTPXMock, monkeypatch):
    """HTML 200 但解析失败时不得误报为 HTTP 200 错误。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        text="<html><body>content</body></html>",
    )

    def fail_parse(_html: str) -> tuple[str, str]:
        raise ValueError("invalid fixture")

    monkeypatch.setattr(ArxivFulltextClient, "_extract_html_text", staticmethod(fail_parse))

    async with ArxivFulltextClient() as client:
        result = await client.get_fulltext("2301.99999")

    assert result.error == "arXiv HTML 解析失败"
    assert result.content == ""
