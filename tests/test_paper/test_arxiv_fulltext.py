"""arXiv 全文获取客户端单元测试（pytest-httpx mock）。

覆盖 ``souwen.paper.arxiv_fulltext`` 中 ArxivFulltextClient 的 HTML 提取、
PDF 回退、错误处理逻辑。无真实网络调用。

测试清单：
- ``test_html_success``：HTML 200 时提取标题与正文
- ``test_html_strips_unwanted_tags``：剥离 nav/script/style 等噪音
- ``test_pdf_fallback_when_html_404``：HTML 404 时回退到 PDF
- ``test_pdf_fallback_without_pymupdf4llm``：未安装 pymupdf4llm 时返回 error
- ``test_both_failed``：HTML/PDF 均失败时返回带 error 的 FetchResult
"""

from __future__ import annotations

import re
from unittest.mock import patch

from pytest_httpx import HTTPXMock

from souwen.paper.arxiv_fulltext import ArxivFulltextClient


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


async def test_pdf_fallback_when_html_404(httpx_mock: HTTPXMock):
    """HTML 404 时回退到 PDF；若 pymupdf4llm 可用则返回 markdown。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        status_code=404,
        text="not found",
    )
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/pdf/.*"),
        content=b"%PDF-1.4 fake content",
    )

    with patch.object(
        ArxivFulltextClient,
        "_pdf_to_markdown",
        return_value="# Title\n\nMocked markdown content.",
    ):
        async with ArxivFulltextClient() as c:
            result = await c.get_fulltext("2301.99999")

    assert result.error is None
    assert result.content_format == "markdown"
    assert "Mocked markdown" in result.content
    assert result.raw["variant"] == "pdf"


async def test_pdf_fallback_without_pymupdf4llm(httpx_mock: HTTPXMock):
    """pymupdf4llm 不可用时（_pdf_to_markdown 返回 None）返回 error 字段。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        status_code=404,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/pdf/.*"),
        content=b"%PDF-1.4 stub",
    )

    with patch.object(ArxivFulltextClient, "_pdf_to_markdown", return_value=None):
        async with ArxivFulltextClient() as c:
            result = await c.get_fulltext("2301.99999")

    assert result.error is not None
    assert "pymupdf4llm" in result.error
    assert result.content == ""


async def test_both_failed(httpx_mock: HTTPXMock):
    """HTML 与 PDF 均非 200 时返回带 error 的 FetchResult。"""
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/html/.*"),
        status_code=404,
    )
    httpx_mock.add_response(
        url=re.compile(r"https://arxiv\.org/pdf/.*"),
        status_code=500,
    )

    async with ArxivFulltextClient() as c:
        result = await c.get_fulltext("2301.99999")

    assert result.error is not None
    assert "500" in result.error
