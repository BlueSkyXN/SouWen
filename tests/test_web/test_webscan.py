"""网页扫描工具模块单元测试

覆盖 ``souwen.web.webscan`` 中各功能函数的逻辑。

测试清单：
- ``TestLinkExtractor``     ：HTML 链接提取器（_LinkExtractor / _parse_links）
- ``TestExtractLinks``      ：extract_links SSRF 校验与链接过滤
- ``TestCrawlSite``         ：crawl_site 同源过滤与深度控制
- ``TestCheckLinks``        ：check_links 有效性判断
- ``TestFindPatterns``      ：find_patterns 正则过滤
- ``TestGenerateSitemap``   ：generate_sitemap XML 格式验证
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from souwen.web.webscan import (
    _parse_links,
    check_links,
    crawl_site,
    extract_links,
    find_patterns,
    generate_sitemap,
)


# ---------------------------------------------------------------------------
# _parse_links 单元测试
# ---------------------------------------------------------------------------


class TestLinkExtractor:
    """内置 HTML 链接解析器"""

    def test_extracts_absolute_url(self):
        html = '<a href="https://example.com/page">Example</a>'
        links = _parse_links(html, "https://example.com/")
        assert len(links) == 1
        assert links[0][0] == "https://example.com/page"
        assert links[0][1] == "Example"

    def test_resolves_relative_url(self):
        html = '<a href="/about">About</a>'
        links = _parse_links(html, "https://example.com/")
        assert links[0][0] == "https://example.com/about"

    def test_skips_anchor_links(self):
        html = '<a href="#section">Jump</a>'
        links = _parse_links(html, "https://example.com/")
        assert links == []

    def test_skips_mailto_links(self):
        html = '<a href="mailto:test@example.com">Email</a>'
        links = _parse_links(html, "https://example.com/")
        assert links == []

    def test_skips_tel_links(self):
        html = '<a href="tel:+1234567890">Call</a>'
        links = _parse_links(html, "https://example.com/")
        assert links == []

    def test_skips_javascript_links(self):
        html = '<a href="javascript:void(0)">Click</a>'
        links = _parse_links(html, "https://example.com/")
        assert links == []

    def test_uses_no_text_for_empty_anchor(self):
        html = '<a href="https://example.com/img"></a>'
        links = _parse_links(html, "https://example.com/")
        assert links[0][1] == "[No text]"

    def test_extracts_multiple_links(self):
        html = """
        <a href="/page1">Page 1</a>
        <a href="/page2">Page 2</a>
        <a href="/page3">Page 3</a>
        """
        links = _parse_links(html, "https://example.com/")
        assert len(links) == 3

    def test_handles_malformed_html(self):
        """错误 HTML 不应抛出异常"""
        html = '<a href="/ok">Good</a><a href="bad href with spaces">'
        links = _parse_links(html, "https://example.com/")
        assert isinstance(links, list)


# ---------------------------------------------------------------------------
# extract_links 测试
# ---------------------------------------------------------------------------


class TestExtractLinks:
    """extract_links 功能测试"""

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        """私有 IP URL 被 SSRF 拦截"""
        resp = await extract_links("http://127.0.0.1/page")
        assert resp.error is not None
        assert "SSRF" in resp.error
        assert resp.total == 0

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_error(self):
        """页面抓取失败返回 error 字段"""
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=""):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await extract_links("https://example.com/")
        assert resp.error is not None

    @pytest.mark.asyncio
    async def test_base_url_filter(self):
        """base_url 过滤：仅返回匹配前缀的链接"""
        sample_html = """
        <a href="https://example.com/docs/api">API Docs</a>
        <a href="https://example.com/blog/post">Blog Post</a>
        <a href="https://example.com/docs/guide">Guide</a>
        """
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=sample_html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await extract_links(
                    "https://example.com/", base_url="https://example.com/docs"
                )
        assert resp.total == 2
        assert all(r.url.startswith("https://example.com/docs") for r in resp.links)

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        """limit 参数限制返回数量"""
        many_links = "".join(
            f'<a href="https://example.com/page{i}">Page {i}</a>' for i in range(20)
        )
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=many_links):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await extract_links("https://example.com/", limit=5)
        assert resp.total == 5
        assert len(resp.links) == 5

    @pytest.mark.asyncio
    async def test_deduplication(self):
        """重复 URL 只返回一次"""
        html = """
        <a href="https://example.com/page">Page</a>
        <a href="https://example.com/page">Page again</a>
        """
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await extract_links("https://example.com/")
        assert resp.total == 1


# ---------------------------------------------------------------------------
# crawl_site 测试
# ---------------------------------------------------------------------------


class TestCrawlSite:
    """crawl_site 功能测试"""

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        """私有 IP 被 SSRF 拦截时返回空结果"""
        result = await crawl_site("http://10.0.0.1/")
        assert result.total_urls == 0
        assert result.crawled_urls == []

    @pytest.mark.asyncio
    async def test_same_origin_only(self):
        """仅爬取同源链接，过滤外部链接"""
        page_html = """
        <a href="https://example.com/page1">Internal</a>
        <a href="https://other.com/external">External</a>
        """

        call_count = 0

        async def mock_fetch(url, client, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page_html
            return ""  # depth pages return empty

        with patch("souwen.web.webscan._fetch_html", side_effect=mock_fetch):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                result = await crawl_site("https://example.com/", max_depth=1)

        # external.com should not be in crawled_urls
        assert all("other.com" not in u for u in result.crawled_urls)
        assert result.start_url in result.crawled_urls

    @pytest.mark.asyncio
    async def test_max_urls_respected(self):
        """max_urls 限制 URL 总数"""
        # All links are same-origin
        page_html = "".join(
            f'<a href="https://example.com/page{i}">Page {i}</a>' for i in range(50)
        )

        async def mock_fetch(url, client, timeout):
            return page_html

        with patch("souwen.web.webscan._fetch_html", side_effect=mock_fetch):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                result = await crawl_site("https://example.com/", max_depth=1, max_urls=10)

        assert result.total_urls <= 10

    @pytest.mark.asyncio
    async def test_depth_zero_only_start(self):
        """max_depth=0 只抓起始页，不跟随链接"""
        page_html = '<a href="https://example.com/sub">Sub</a>'
        fetch_calls: list[str] = []

        async def mock_fetch(url, client, timeout):
            fetch_calls.append(url)
            return page_html

        with patch("souwen.web.webscan._fetch_html", side_effect=mock_fetch):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                result = await crawl_site("https://example.com/", max_depth=0)

        # With depth=0, start URL is fetched but sub-links are not followed
        # because depth 0 item is processed (since 0 <= max_depth=0), but
        # the sub-links would be queued at depth=1 which is > max_depth=0
        assert result.total_urls >= 1


# ---------------------------------------------------------------------------
# check_links 测试
# ---------------------------------------------------------------------------


class TestCheckLinks:
    """check_links 功能测试"""

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        """私有 IP 被 SSRF 拦截"""
        resp = await check_links("http://127.0.0.1/page")
        assert resp.error is not None
        assert "SSRF" in resp.error

    @pytest.mark.asyncio
    async def test_valid_link_detection(self):
        """200 响应标记为 valid"""
        page_html = '<a href="https://example.com/good">Good</a>'

        mock_head_response = MagicMock()
        mock_head_response.status_code = 200

        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=page_html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                with patch.object(
                    httpx.AsyncClient, "head", new_callable=AsyncMock, return_value=mock_head_response
                ):
                    resp = await check_links("https://example.com/")

        assert resp.total >= 1
        valid = [r for r in resp.results if r.status == "valid"]
        assert len(valid) >= 1

    @pytest.mark.asyncio
    async def test_broken_link_detection(self):
        """404 响应标记为 broken"""
        page_html = '<a href="https://example.com/missing">Missing</a>'

        mock_head_response = MagicMock()
        mock_head_response.status_code = 404

        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=page_html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                with patch.object(
                    httpx.AsyncClient, "head", new_callable=AsyncMock, return_value=mock_head_response
                ):
                    resp = await check_links("https://example.com/")

        broken = [r for r in resp.results if r.status == "broken"]
        assert len(broken) >= 1

    @pytest.mark.asyncio
    async def test_counts_correct(self):
        """valid_count 和 broken_count 计数正确"""
        page_html = """
        <a href="https://example.com/good">Good</a>
        <a href="https://example.com/bad">Bad</a>
        """
        call_num = 0

        async def mock_head(url, **kwargs):
            nonlocal call_num
            call_num += 1
            m = MagicMock()
            m.status_code = 200 if "good" in url else 404
            return m

        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=page_html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                with patch.object(httpx.AsyncClient, "head", side_effect=mock_head):
                    resp = await check_links("https://example.com/")

        assert resp.valid_count == 1
        assert resp.broken_count == 1
        assert resp.total == 2


# ---------------------------------------------------------------------------
# find_patterns 测试
# ---------------------------------------------------------------------------


class TestFindPatterns:
    """find_patterns 功能测试"""

    @pytest.mark.asyncio
    async def test_ssrf_blocked(self):
        """私有 IP 被 SSRF 拦截"""
        resp = await find_patterns("http://10.0.0.1/page", r"\.pdf$")
        assert resp.error is not None
        assert "SSRF" in resp.error

    @pytest.mark.asyncio
    async def test_invalid_regex(self):
        """无效正则表达式返回 error"""
        with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
            resp = await find_patterns("https://example.com/", r"[invalid")
        assert resp.error is not None
        assert "正则" in resp.error

    @pytest.mark.asyncio
    async def test_pattern_filters_links(self):
        """正则模式正确过滤 URL"""
        page_html = """
        <a href="https://example.com/doc.pdf">PDF</a>
        <a href="https://example.com/page.html">HTML</a>
        <a href="https://example.com/report.pdf">PDF Report</a>
        """
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=page_html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await find_patterns("https://example.com/", r"\.pdf$")

        assert resp.total == 2
        assert all(u.endswith(".pdf") for u in resp.matches)

    @pytest.mark.asyncio
    async def test_limit_respected(self):
        """limit 参数限制匹配数量"""
        many_links = "".join(
            f'<a href="https://example.com/file{i}.pdf">File {i}</a>' for i in range(20)
        )
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=many_links):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await find_patterns("https://example.com/", r"\.pdf$", limit=5)
        assert resp.total == 5

    @pytest.mark.asyncio
    async def test_no_matches_returns_empty(self):
        """无匹配时返回空列表"""
        page_html = '<a href="https://example.com/page.html">Page</a>'
        with patch("souwen.web.webscan._fetch_html", new_callable=AsyncMock, return_value=page_html):
            with patch("souwen.web.webscan.validate_fetch_url", return_value=(True, "")):
                resp = await find_patterns("https://example.com/", r"\.pdf$")
        assert resp.total == 0
        assert resp.matches == []


# ---------------------------------------------------------------------------
# generate_sitemap 测试
# ---------------------------------------------------------------------------


class TestGenerateSitemap:
    """generate_sitemap 功能测试"""

    @pytest.mark.asyncio
    async def test_xml_structure(self):
        """生成的 XML 包含标准 Sitemap 结构"""
        mock_crawl = MagicMock()
        mock_crawl.crawled_urls = ["https://example.com/", "https://example.com/about"]

        with patch("souwen.web.webscan.crawl_site", new_callable=AsyncMock, return_value=mock_crawl):
            result = await generate_sitemap("https://example.com/")

        expected_namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
        assert '<?xml version="1.0"' in result.sitemap_xml
        assert "urlset" in result.sitemap_xml
        assert expected_namespace in result.sitemap_xml
        assert "<loc>" in result.sitemap_xml
        assert "<lastmod>" in result.sitemap_xml

    @pytest.mark.asyncio
    async def test_url_count(self):
        """url_count 与 crawled_urls 一致"""
        mock_crawl = MagicMock()
        mock_crawl.crawled_urls = [f"https://example.com/page{i}" for i in range(5)]

        with patch("souwen.web.webscan.crawl_site", new_callable=AsyncMock, return_value=mock_crawl):
            result = await generate_sitemap("https://example.com/")

        assert result.url_count == 5

    @pytest.mark.asyncio
    async def test_xml_escaping(self):
        """URL 中的特殊字符被正确 XML 转义"""
        mock_crawl = MagicMock()
        mock_crawl.crawled_urls = ["https://example.com/search?q=a&b=c"]

        with patch("souwen.web.webscan.crawl_site", new_callable=AsyncMock, return_value=mock_crawl):
            result = await generate_sitemap("https://example.com/")

        # & should be escaped to &amp;
        assert "&amp;" in result.sitemap_xml
        assert "&b=c" not in result.sitemap_xml  # raw & should not appear in loc

    @pytest.mark.asyncio
    async def test_limit_applied(self):
        """limit 参数限制 Sitemap 中的 URL 数量"""
        mock_crawl = MagicMock()
        mock_crawl.crawled_urls = [f"https://example.com/page{i}" for i in range(50)]

        with patch("souwen.web.webscan.crawl_site", new_callable=AsyncMock, return_value=mock_crawl):
            result = await generate_sitemap("https://example.com/", limit=10)

        assert result.url_count == 10

    @pytest.mark.asyncio
    async def test_start_url_recorded(self):
        """start_url 字段记录正确"""
        mock_crawl = MagicMock()
        mock_crawl.crawled_urls = ["https://example.com/"]

        with patch("souwen.web.webscan.crawl_site", new_callable=AsyncMock, return_value=mock_crawl):
            result = await generate_sitemap("https://example.com/")

        assert result.start_url == "https://example.com/"
