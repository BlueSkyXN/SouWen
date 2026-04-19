"""内置网页抓取客户端单元测试

覆盖 ``souwen.web.builtin`` 中 BuiltinFetcherClient 的抓取、提取、批量处理逻辑。

测试清单：
- ``test_extract_fallback_strips_html``    ：纯正则回退提取正文
- ``test_extract_with_trafilatura_fallback``：trafilatura 不可用时降级
- ``test_fetch_single_ok``                 ：成功抓取单个 URL
- ``test_fetch_single_error``              ：网络错误返回 error 字段
- ``test_fetch_single_short_page``         ：过短页面返回错误
- ``test_fetch_batch_concurrency``         ：批量并发抓取
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from souwen.web.builtin import (
    BuiltinFetcherClient,
    _extract_fallback,
    _extract_with_trafilatura,
)


class TestExtractFallback:
    """纯正则回退提取"""

    def test_strips_html_tags(self):
        html = "<html><body><p>Hello <b>world</b></p></body></html>"
        text = _extract_fallback(html)
        assert "Hello" in text
        assert "world" in text
        assert "<" not in text

    def test_strips_script_and_style(self):
        html = "<script>alert('xss')</script><style>.x{}</style><p>Content</p>"
        text = _extract_fallback(html)
        assert "alert" not in text
        assert "Content" in text


class TestExtractWithTrafilatura:
    """trafilatura 提取（可能回退到 html2text 或 regex）"""

    def test_returns_dict_keys(self):
        """结果包含必要字段"""
        html = (
            "<html><body><article><p>This is a long enough article body text for extraction testing purposes. "
            * 5
            + "</p></article></body></html>"
        )
        result = _extract_with_trafilatura(html, "https://example.com")
        assert "content" in result
        assert "title" in result
        assert "content_format" in result

    def test_empty_html_fallback(self):
        """空 HTML 回退到 regex"""
        result = _extract_with_trafilatura("", "https://example.com")
        assert result["content"] == ""


class TestBuiltinFetcherSingle:
    """单 URL 抓取"""

    @pytest.mark.asyncio
    async def test_fetch_ok(self):
        """成功抓取返回 FetchResult"""
        html = (
            "<html><head><title>Test</title></head>"
            "<body><article><p>" + "This is test content. " * 20 + "</p></article></body></html>"
        )
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/page"

        with patch.object(BuiltinFetcherClient, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            async with BuiltinFetcherClient() as client:
                result = await client.fetch("https://example.com/page")

        assert result.error is None
        assert result.source == "builtin"
        assert result.url == "https://example.com/page"
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        """网络异常返回 error"""
        with patch.object(
            BuiltinFetcherClient,
            "_fetch",
            new_callable=AsyncMock,
            side_effect=Exception("connect timeout"),
        ):
            async with BuiltinFetcherClient() as client:
                result = await client.fetch("https://example.com/fail")

        assert result.error is not None
        assert "connect timeout" in result.error
        assert result.source == "builtin"

    @pytest.mark.asyncio
    async def test_fetch_short_page(self):
        """过短页面报错"""
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>Hi</body></html>"
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/tiny"

        with patch.object(BuiltinFetcherClient, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            async with BuiltinFetcherClient() as client:
                result = await client.fetch("https://example.com/tiny")

        assert result.error is not None
        assert "过短" in result.error or "为空" in result.error


class TestBuiltinFetcherBatch:
    """批量抓取"""

    @pytest.mark.asyncio
    async def test_batch_returns_response(self):
        """fetch_batch 返回 FetchResponse"""
        html = "<html><body><article><p>" + "Batch content. " * 20 + "</p></article></body></html>"
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/batch"

        urls = ["https://example.com/a", "https://example.com/b"]

        with patch.object(BuiltinFetcherClient, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_resp
            async with BuiltinFetcherClient() as client:
                resp = await client.fetch_batch(urls)

        assert resp.provider == "builtin"
        assert resp.total == 2
        assert resp.total_ok == 2
        assert resp.total_failed == 0
        assert len(resp.results) == 2
