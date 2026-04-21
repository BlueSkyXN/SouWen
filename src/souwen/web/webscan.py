"""网页扫描工具模块

文件用途：
    提供网页链接提取、网站爬取、链接有效性检查、URL 模式匹配和 Sitemap 生成功能。
    基于 httpx 异步 HTTP 客户端，使用 asyncio.Semaphore 控制并发。
    参考 mcp-server-webscan 的功能设计，以 SouWen Python 架构重新实现。

函数清单：
    extract_links(url, base_url, limit, timeout) -> ExtractLinksResponse
        - 从指定页面提取所有链接，可按 base_url 过滤并限制数量
    crawl_site(url, max_depth, max_urls, concurrency, timeout) -> CrawlResult
        - 递归爬取网站（仅同源链接），使用 asyncio.Semaphore 控制并发
    check_links(url, concurrency, timeout) -> CheckLinksResponse
        - 对页面上每个链接发起 HEAD 请求，判断有效（2xx）或失效
    find_patterns(url, pattern, limit, timeout) -> FindPatternsResponse
        - 从页面提取链接并用正则表达式过滤，返回匹配 URL 列表
    generate_sitemap(url, max_depth, limit, timeout) -> SitemapResult
        - 爬取网站并输出标准 XML Sitemap 格式

模块依赖：
    - asyncio: 异步并发控制
    - re: 正则表达式匹配
    - xml.sax.saxutils: XML 特殊字符转义
    - datetime: 生成 lastmod 日期
    - html.parser: 内置 HTML 解析（链接提取）
    - urllib.parse: URL 拼接与解析
    - httpx: 异步 HTTP 请求
    - souwen.http_client: DEFAULT_USER_AGENT
    - souwen.models: ExtractLinksResponse, CrawlResult, CheckLinksResponse,
                     FindPatternsResponse, SitemapResult, LinkResult, LinkCheckResult
    - souwen.web.fetch: validate_fetch_url（SSRF 防护）
"""

from __future__ import annotations

import asyncio
import re
import xml.sax.saxutils as saxutils
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from souwen.http_client import DEFAULT_USER_AGENT
from souwen.models import (
    CheckLinksResponse,
    CrawlResult,
    ExtractLinksResponse,
    FindPatternsResponse,
    LinkCheckResult,
    LinkResult,
    SitemapResult,
)
from souwen.web.fetch import validate_fetch_url


# ---------------------------------------------------------------------------
# 内部 HTML 链接解析器
# ---------------------------------------------------------------------------


class _LinkExtractor(HTMLParser):
    """从 HTML 提取 <a href> 链接的内置解析器"""

    def __init__(self, page_url: str) -> None:
        super().__init__()
        self._page_url = page_url
        self.links: list[tuple[str, str]] = []  # (absolute_url, anchor_text)
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            attrs_dict = dict(attrs)
            href = (attrs_dict.get("href") or "").strip()
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                try:
                    self._current_href = urljoin(self._page_url, href)
                    self._current_text = []
                except Exception:
                    self._current_href = None

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href is not None:
            text = "".join(self._current_text).strip() or "[No text]"
            self.links.append((self._current_href, text))
            self._current_href = None
            self._current_text = []


def _parse_links(html: str, page_url: str) -> list[tuple[str, str]]:
    """从 HTML 提取链接，返回 (absolute_url, anchor_text) 列表

    Args:
        html: 原始 HTML 文本
        page_url: 当前页面 URL（用于将相对 URL 转为绝对 URL）

    Returns:
        (absolute_url, anchor_text) 元组列表
    """
    try:
        extractor = _LinkExtractor(page_url)
        extractor.feed(html)
        return extractor.links
    except Exception:
        return []


async def _fetch_html(url: str, client: httpx.AsyncClient, timeout: float) -> str:
    """抓取目标页面 HTML 文本

    Args:
        url: 目标 URL
        client: 已配置的 httpx 异步客户端
        timeout: 请求超时（秒）

    Returns:
        HTML 字符串；失败时返回空字符串
    """
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


async def extract_links(
    url: str,
    base_url: str | None = None,
    limit: int = 100,
    timeout: float = 10.0,
) -> ExtractLinksResponse:
    """从网页提取所有链接

    发起 GET 请求获取页面 HTML，使用内置 HTML 解析器提取所有 <a href> 链接。
    支持按 base_url 前缀过滤，并通过 limit 参数限制返回数量。
    对起始 URL 执行 SSRF 防护校验。

    Args:
        url: 目标页面 URL
        base_url: 可选过滤前缀（仅返回以此开头的链接）
        limit: 最大返回链接数量，默认 100
        timeout: HTTP 请求超时秒数，默认 10.0

    Returns:
        ExtractLinksResponse，包含链接列表和总数；失败时 error 字段包含原因
    """
    is_valid, reason = validate_fetch_url(url)
    if not is_valid:
        return ExtractLinksResponse(url=url, error=f"SSRF 校验失败: {reason}")

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        ) as client:
            html = await _fetch_html(url, client, timeout)

        if not html:
            return ExtractLinksResponse(url=url, error="页面抓取失败或返回空内容")

        raw_links = _parse_links(html, url)

        filtered: list[LinkResult] = []
        seen: set[str] = set()
        for link_url, text in raw_links:
            if base_url and not link_url.startswith(base_url):
                continue
            if link_url in seen:
                continue
            seen.add(link_url)
            filtered.append(LinkResult(url=link_url, text=text))
            if len(filtered) >= limit:
                break

        return ExtractLinksResponse(url=url, links=filtered, total=len(filtered))

    except Exception as exc:
        return ExtractLinksResponse(url=url, error=str(exc))


async def crawl_site(
    url: str,
    max_depth: int = 2,
    max_urls: int = 500,
    concurrency: int = 10,
    timeout: float = 10.0,
) -> CrawlResult:
    """递归爬取网站（仅限同源链接）

    从起始 URL 开始，BFS 遍历同源页面；使用 asyncio.Semaphore 控制并发度。
    对起始 URL 执行 SSRF 防护校验。

    Args:
        url: 爬取起始 URL
        max_depth: 最大爬取深度，默认 2（0 表示仅抓起始页）
        max_urls: 最大 URL 总量，默认 500
        concurrency: 并发请求数，默认 10
        timeout: 每页请求超时秒数，默认 10.0

    Returns:
        CrawlResult，包含所有发现的 URL 列表和总数
    """
    is_valid, reason = validate_fetch_url(url)
    if not is_valid:
        return CrawlResult(
            start_url=url, crawled_urls=[], total_urls=0, max_depth=max_depth
        )

    parsed_start = urlparse(url)
    base_origin = f"{parsed_start.scheme}://{parsed_start.netloc}"

    visited: set[str] = {url}
    crawled: list[str] = [url]
    queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
    queue.put_nowait((url, 0))
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    ) as client:
        while not queue.empty() and len(crawled) < max_urls:
            batch: list[tuple[str, int]] = []
            while not queue.empty() and len(batch) < concurrency:
                batch.append(queue.get_nowait())

            async def process_one(item: tuple[str, int]) -> None:
                page_url, depth = item
                if depth >= max_depth:
                    return
                async with sem:
                    try:
                        html = await _fetch_html(page_url, client, timeout)
                        if not html:
                            return
                        links = _parse_links(html, page_url)
                        for link_url, _ in links:
                            parsed = urlparse(link_url)
                            link_origin = f"{parsed.scheme}://{parsed.netloc}"
                            if link_origin == base_origin and link_url not in visited:
                                visited.add(link_url)
                                crawled.append(link_url)
                                if len(crawled) < max_urls:
                                    queue.put_nowait((link_url, depth + 1))
                    except Exception:
                        pass

            await asyncio.gather(*[process_one(item) for item in batch])

    return CrawlResult(
        start_url=url,
        crawled_urls=crawled,
        total_urls=len(crawled),
        max_depth=max_depth,
    )


async def check_links(
    url: str,
    concurrency: int = 10,
    timeout: float = 10.0,
) -> CheckLinksResponse:
    """检查页面上所有链接的有效性

    先抓取页面并提取链接，然后对每个链接发起 HEAD 请求（2xx 为 valid，其余为 broken）。
    对起始 URL 执行 SSRF 防护校验；被检查链接不做 SSRF 校验（允许检查外部链接）。

    Args:
        url: 目标页面 URL
        concurrency: 并发检查数，默认 10
        timeout: 每链接超时秒数，默认 10.0

    Returns:
        CheckLinksResponse，包含各链接检查结果、有效数和失效数
    """
    is_valid, reason = validate_fetch_url(url)
    if not is_valid:
        return CheckLinksResponse(url=url, error=f"SSRF 校验失败: {reason}")

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        ) as client:
            html = await _fetch_html(url, client, timeout)
            if not html:
                return CheckLinksResponse(url=url, error="页面抓取失败或返回空内容")

            raw_links = _parse_links(html, url)
            seen: set[str] = set()
            unique_links: list[str] = []
            for link_url, _ in raw_links:
                if link_url not in seen:
                    seen.add(link_url)
                    unique_links.append(link_url)

            sem = asyncio.Semaphore(concurrency)
            results: list[LinkCheckResult] = []

            async def check_one(link_url: str) -> LinkCheckResult:
                async with sem:
                    try:
                        parsed = urlparse(link_url)
                        if parsed.scheme not in ("http", "https"):
                            return LinkCheckResult(
                                url=link_url, status="invalid_url", error="不支持的协议"
                            )
                        resp = await client.head(
                            link_url, timeout=timeout, follow_redirects=True
                        )
                        if 200 <= resp.status_code < 300:
                            return LinkCheckResult(
                                url=link_url,
                                status="valid",
                                status_code=resp.status_code,
                            )
                        return LinkCheckResult(
                            url=link_url,
                            status="broken",
                            status_code=resp.status_code,
                        )
                    except Exception as exc:
                        return LinkCheckResult(
                            url=link_url, status="error", error=str(exc)
                        )

            results = list(
                await asyncio.gather(*[check_one(link_url) for link_url in unique_links])
            )

        valid_count = sum(1 for r in results if r.status == "valid")
        broken_count = sum(1 for r in results if r.status != "valid")
        return CheckLinksResponse(
            url=url,
            results=results,
            total=len(results),
            valid_count=valid_count,
            broken_count=broken_count,
        )

    except Exception as exc:
        return CheckLinksResponse(url=url, error=str(exc))


async def find_patterns(
    url: str,
    pattern: str,
    limit: int = 100,
    timeout: float = 10.0,
) -> FindPatternsResponse:
    """从页面提取链接并按正则表达式模式过滤

    抓取页面、提取所有链接后，用正则表达式对每个 URL 进行匹配，
    返回匹配的 URL 列表（去重）。

    Args:
        url: 目标页面 URL
        pattern: 正则表达式模式字符串
        limit: 最大返回数量，默认 100
        timeout: HTTP 请求超时秒数，默认 10.0

    Returns:
        FindPatternsResponse，包含匹配 URL 列表和总数；失败时 error 字段包含原因
    """
    is_valid, reason = validate_fetch_url(url)
    if not is_valid:
        return FindPatternsResponse(
            url=url, pattern=pattern, error=f"SSRF 校验失败: {reason}"
        )

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return FindPatternsResponse(
            url=url, pattern=pattern, error=f"正则表达式无效: {exc}"
        )

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        ) as client:
            html = await _fetch_html(url, client, timeout)

        if not html:
            return FindPatternsResponse(
                url=url, pattern=pattern, error="页面抓取失败或返回空内容"
            )

        raw_links = _parse_links(html, url)
        matches: list[str] = []
        seen: set[str] = set()
        for link_url, _ in raw_links:
            if link_url in seen:
                continue
            if compiled.search(link_url):
                seen.add(link_url)
                matches.append(link_url)
                if len(matches) >= limit:
                    break

        return FindPatternsResponse(
            url=url, pattern=pattern, matches=matches, total=len(matches)
        )

    except Exception as exc:
        return FindPatternsResponse(url=url, pattern=pattern, error=str(exc))


async def generate_sitemap(
    url: str,
    max_depth: int = 2,
    limit: int = 1000,
    timeout: float = 10.0,
) -> SitemapResult:
    """爬取网站并生成 XML Sitemap

    调用 crawl_site 递归爬取同源页面，然后将发现的所有 URL 格式化为标准
    XML Sitemap（https://www.sitemaps.org/schemas/sitemap/0.9）。

    Args:
        url: 起始 URL
        max_depth: 最大爬取深度，默认 2
        limit: Sitemap 最大 URL 数量，默认 1000
        timeout: 每页请求超时秒数，默认 10.0

    Returns:
        SitemapResult，包含 XML 字符串和 URL 数量
    """
    crawl = await crawl_site(
        url, max_depth=max_depth, max_urls=limit, timeout=timeout
    )
    urls = crawl.crawled_urls[:limit]
    today = date.today().isoformat()

    url_entries = "\n".join(
        f"  <url>\n    <loc>{saxutils.escape(u)}</loc>\n    <lastmod>{today}</lastmod>\n  </url>"
        for u in urls
    )
    sitemap_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{url_entries}\n"
        "</urlset>"
    )

    return SitemapResult(start_url=url, sitemap_xml=sitemap_xml, url_count=len(urls))
