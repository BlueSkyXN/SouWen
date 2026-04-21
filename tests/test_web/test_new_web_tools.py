"""新 Web 工具单元测试

覆盖 link extraction、sitemap parsing、CSS selector fetch 的核心逻辑。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Link Extraction Tests
# ---------------------------------------------------------------------------

class TestLinkModels:
    """LinkItem / LinkExtractionResult 模型测试"""

    def test_link_item_basic(self):
        from souwen.web.links import LinkItem
        item = LinkItem(url="https://example.com", text="Example")
        assert item.url == "https://example.com"
        assert item.text == "Example"

    def test_link_item_empty_text(self):
        from souwen.web.links import LinkItem
        item = LinkItem(url="https://example.com")
        assert item.text == ""

    def test_link_extraction_result_basic(self):
        from souwen.web.links import LinkExtractionResult, LinkItem
        result = LinkExtractionResult(
            source_url="https://example.com",
            final_url="https://example.com",
            links=[LinkItem(url="https://example.com/a", text="A")],
            total=1,
            filtered_count=2,
        )
        assert result.total == 1
        assert result.filtered_count == 2
        assert result.error is None
        assert len(result.links) == 1

    def test_link_extraction_result_error(self):
        from souwen.web.links import LinkExtractionResult
        result = LinkExtractionResult(
            source_url="https://example.com",
            error="SSRF blocked",
        )
        assert result.error == "SSRF blocked"
        assert result.total == 0
        assert result.links == []


class _FakeResp:
    """Fake httpx-like response for mocking BaseScraper._fetch."""

    def __init__(self, html: str, url: str = "https://example.com/"):
        self.text = html
        self.url = url
        self.content = html.encode("utf-8")
        self.status_code = 200


class _FakeScraper:
    """Async-context-manager scraper returning a preset response."""

    def __init__(self, resp: _FakeResp):
        self._resp = resp

    def __init_args__(self, *a, **kw):  # pragma: no cover
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _fetch(self, url: str):
        return self._resp


def _patch_scraper(html: str, url: str = "https://example.com/"):
    """Helper: patch BaseScraper symbol used inside extract_links."""
    resp = _FakeResp(html, url)
    return patch(
        "souwen.scraper.base.BaseScraper",
        lambda *a, **kw: _FakeScraper(resp),
    )


class TestExtractLinks:
    """extract_links 异步函数测试（通过 mock HTTP 层）"""

    async def test_extract_links_ssrf_blocked(self):
        """SSRF 校验失败的 URL 应直接返回错误"""
        from souwen.web.links import extract_links

        with patch(
            "souwen.web.fetch.validate_fetch_url",
            return_value=(False, "private IP"),
        ):
            result = await extract_links("http://192.168.1.1/page")
        assert result.error is not None
        assert "SSRF" in result.error
        assert result.total == 0

    async def test_extract_links_basic_and_skip_schemes(self):
        """常规链接、相对链接保留；fragment / mailto / javascript / tel 跳过"""
        from souwen.web.links import extract_links

        html = """
        <html><body>
            <a href="https://example.com/a">A</a>
            <a href="/b">B</a>
            <a href="#section">Skip frag</a>
            <a href="mailto:x@y.com">mail</a>
            <a href="javascript:void(0)">js</a>
            <a href="tel:+123">tel</a>
            <a href="https://example.com/a">Dup</a>
        </body></html>
        """
        with patch("souwen.web.fetch.validate_fetch_url", return_value=(True, "ok")), \
             _patch_scraper(html, "https://example.com/"):
            result = await extract_links("https://example.com/")

        assert result.error is None
        urls = [link.url for link in result.links]
        # dedup → only one /a, plus /b
        assert "https://example.com/a" in urls
        assert "https://example.com/b" in urls
        # skip schemes
        assert not any(u.startswith("mailto:") for u in urls)
        assert not any(u.startswith("javascript:") for u in urls)
        assert not any(u.startswith("tel:") for u in urls)
        assert not any("#section" in u for u in urls)
        assert result.total == 2

    async def test_extract_links_base_href(self):
        """<base href> 应作为相对链接解析的基准"""
        from souwen.web.links import extract_links

        html = """
        <html><head><base href="https://other.example.org/path/"></head>
        <body><a href="page.html">P</a></body></html>
        """
        with patch("souwen.web.fetch.validate_fetch_url", return_value=(True, "ok")), \
             _patch_scraper(html, "https://example.com/"):
            result = await extract_links("https://example.com/")

        assert result.error is None
        assert result.total == 1
        assert result.links[0].url == "https://other.example.org/path/page.html"

    async def test_extract_links_base_url_filter(self):
        """base_url_filter 应过滤掉不匹配前缀的链接"""
        from souwen.web.links import extract_links

        html = """
        <html><body>
            <a href="https://example.com/keep">k</a>
            <a href="https://other.com/drop">d</a>
        </body></html>
        """
        with patch("souwen.web.fetch.validate_fetch_url", return_value=(True, "ok")), \
             _patch_scraper(html, "https://example.com/"):
            result = await extract_links(
                "https://example.com/",
                base_url_filter="https://example.com/",
            )

        urls = [link.url for link in result.links]
        assert urls == ["https://example.com/keep"]
        assert result.filtered_count == 1

    async def test_extract_links_limit(self):
        """limit 应截断返回数量"""
        from souwen.web.links import extract_links

        anchors = "".join(
            f'<a href="https://example.com/p{i}">p{i}</a>' for i in range(20)
        )
        html = f"<html><body>{anchors}</body></html>"
        with patch("souwen.web.fetch.validate_fetch_url", return_value=(True, "ok")), \
             _patch_scraper(html, "https://example.com/"):
            result = await extract_links("https://example.com/", limit=5)

        assert result.total == 5
        assert len(result.links) == 5

    async def test_extract_links_ssrf_filtered_in_page(self):
        """页面内提取的链接若 SSRF 校验失败应计入 filtered_count"""
        from souwen.web.links import extract_links

        html = """
        <html><body>
            <a href="https://good.example.com/x">good</a>
            <a href="http://10.0.0.1/bad">bad</a>
        </body></html>
        """

        def _fake_validate(url, *a, **kw):
            # 入口 URL + good.example.com 通过；10.x 拒绝
            if "10.0.0.1" in url:
                return (False, "private IP")
            return (True, "ok")

        with patch("souwen.web.fetch.validate_fetch_url", side_effect=_fake_validate), \
             _patch_scraper(html, "https://example.com/"):
            result = await extract_links("https://example.com/")

        urls = [link.url for link in result.links]
        assert "https://good.example.com/x" in urls
        assert all("10.0.0.1" not in u for u in urls)
        assert result.filtered_count == 1


# ---------------------------------------------------------------------------
# Sitemap Parsing Tests
# ---------------------------------------------------------------------------

class TestSitemapParsing:
    """Sitemap XML 解析测试"""

    def test_parse_urlset(self):
        from souwen.web.sitemap import _parse_sitemap_xml
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/page1</loc>
                <lastmod>2024-01-01</lastmod>
                <changefreq>weekly</changefreq>
                <priority>0.8</priority>
            </url>
            <url>
                <loc>https://example.com/page2</loc>
            </url>
        </urlset>"""
        entries, children = _parse_sitemap_xml(xml)
        assert len(entries) == 2
        assert entries[0].loc == "https://example.com/page1"
        assert entries[0].lastmod == "2024-01-01"
        assert entries[0].changefreq == "weekly"
        assert entries[0].priority == 0.8
        assert entries[1].loc == "https://example.com/page2"
        assert entries[1].lastmod is None
        assert len(children) == 0

    def test_parse_sitemapindex(self):
        from souwen.web.sitemap import _parse_sitemap_xml
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap>
                <loc>https://example.com/sitemap1.xml</loc>
            </sitemap>
            <sitemap>
                <loc>https://example.com/sitemap2.xml</loc>
            </sitemap>
        </sitemapindex>"""
        entries, children = _parse_sitemap_xml(xml)
        assert len(entries) == 0
        assert len(children) == 2
        assert children[0] == "https://example.com/sitemap1.xml"
        assert children[1] == "https://example.com/sitemap2.xml"

    def test_parse_no_namespace(self):
        """Without xmlns namespace"""
        from souwen.web.sitemap import _parse_sitemap_xml
        xml = b"""<?xml version="1.0"?>
        <urlset>
            <url><loc>https://example.com/</loc></url>
        </urlset>"""
        entries, children = _parse_sitemap_xml(xml)
        assert len(entries) == 1
        assert entries[0].loc == "https://example.com/"
        assert len(children) == 0

    def test_safe_float(self):
        from souwen.web.sitemap import _safe_float
        assert _safe_float("0.8") == 0.8
        assert _safe_float("1.0") == 1.0
        assert _safe_float(" 0.5 ") == 0.5
        assert _safe_float(None) is None
        assert _safe_float("invalid") is None
        assert _safe_float("") is None

    def test_extract_sitemaps_from_robots(self):
        from souwen.web.sitemap import _extract_sitemaps_from_robots
        robots = """User-agent: *
Disallow: /admin/
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap-news.xml
"""
        result = _extract_sitemaps_from_robots(robots, "https://example.com")
        assert len(result) == 2
        assert result[0] == "https://example.com/sitemap.xml"
        assert result[1] == "https://example.com/sitemap-news.xml"

    def test_extract_sitemaps_from_robots_empty(self):
        from souwen.web.sitemap import _extract_sitemaps_from_robots
        robots = """User-agent: *
Disallow: /
"""
        result = _extract_sitemaps_from_robots(robots, "https://example.com")
        assert len(result) == 0

    def test_extract_sitemaps_case_insensitive(self):
        from souwen.web.sitemap import _extract_sitemaps_from_robots
        robots = (
            "SITEMAP: https://example.com/sitemap.xml\n"
            "sitemap: https://example.com/other.xml"
        )
        result = _extract_sitemaps_from_robots(robots, "https://example.com")
        assert len(result) == 2

    def test_extract_sitemaps_relative_resolved(self):
        """robots.txt 中的相对 sitemap 路径应通过 base_url 解析为绝对地址"""
        from souwen.web.sitemap import _extract_sitemaps_from_robots
        robots = "Sitemap: /sitemap.xml"
        result = _extract_sitemaps_from_robots(robots, "https://example.com")
        assert len(result) == 1
        assert result[0] == "https://example.com/sitemap.xml"


class TestSitemapModels:
    """Sitemap model 测试"""

    def test_sitemap_entry(self):
        from souwen.web.sitemap import SitemapEntry
        entry = SitemapEntry(
            loc="https://example.com/page",
            lastmod="2024-06-01",
            priority=0.5,
        )
        assert entry.loc == "https://example.com/page"
        assert entry.lastmod == "2024-06-01"
        assert entry.priority == 0.5
        assert entry.changefreq is None

    def test_sitemap_entry_minimal(self):
        from souwen.web.sitemap import SitemapEntry
        entry = SitemapEntry(loc="https://example.com/")
        assert entry.loc == "https://example.com/"
        assert entry.lastmod is None
        assert entry.changefreq is None
        assert entry.priority is None

    def test_sitemap_result_defaults(self):
        from souwen.web.sitemap import SitemapResult
        result = SitemapResult(root_url="https://example.com")
        assert result.root_url == "https://example.com"
        assert result.total == 0
        assert result.sitemaps_parsed == 0
        assert result.entries == []
        assert result.errors == []


# ---------------------------------------------------------------------------
# CSS Selector + Fetch Params Tests
# ---------------------------------------------------------------------------

class TestFetchParams:
    """fetch 参数签名测试"""

    def test_builtin_fetch_accepts_selector(self):
        """BuiltinFetcherClient.fetch() 应接受 selector / 分页 / robots 参数"""
        import inspect
        from souwen.web.builtin import BuiltinFetcherClient
        sig = inspect.signature(BuiltinFetcherClient.fetch)
        params = list(sig.parameters.keys())
        assert "selector" in params
        assert "start_index" in params
        assert "max_length" in params
        assert "respect_robots_txt" in params

    def test_fetch_content_accepts_new_params(self):
        """fetch_content() 应接受 selector / 分页 / robots 参数"""
        import inspect
        from souwen.web.fetch import fetch_content
        sig = inspect.signature(fetch_content)
        params = list(sig.parameters.keys())
        assert "selector" in params
        assert "start_index" in params
        assert "max_length" in params
        assert "respect_robots_txt" in params

    def test_fetch_request_schema_has_new_fields(self):
        """FetchRequest model 应包含 selector / start_index / max_length / respect_robots_txt"""
        from souwen.server.schemas import FetchRequest
        fields = FetchRequest.model_fields
        assert "selector" in fields
        assert "start_index" in fields
        assert "max_length" in fields
        assert "respect_robots_txt" in fields


# 标记：本模块所有 async test 默认走 pytest-asyncio auto 模式
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")
