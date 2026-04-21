"""网页链接提取工具

文件用途：
    从指定 URL 的页面中提取所有 <a href> 链接，返回结构化的链接列表。
    支持 SSRF 过滤、相对 URL 解析、<base href> 处理、URL 前缀过滤。

函数清单：
    extract_links(url, base_url_filter, limit) -> LinkExtractionResult
        - 功能：抓取页面并提取链接

    LinkItem(BaseModel)
        - url: 绝对 URL
        - text: 链接文本

    LinkExtractionResult(BaseModel)
        - source_url: 源页面 URL
        - final_url: 最终 URL (重定向后)
        - links: list[LinkItem]
        - total: int
        - filtered_count: int (被 SSRF/前缀过滤掉的数量)
        - error: str | None
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger("souwen.web.links")


class LinkItem(BaseModel):
    """单个提取的链接"""

    url: str
    text: str = ""


class LinkExtractionResult(BaseModel):
    """链接提取结果"""

    source_url: str
    final_url: str = ""
    links: list[LinkItem] = Field(default_factory=list)
    total: int = 0
    filtered_count: int = 0
    error: str | None = None


_SKIP_SCHEMES = frozenset({"javascript", "mailto", "tel", "data", "ftp"})


async def extract_links(
    url: str,
    base_url_filter: str | None = None,
    limit: int = 100,
) -> LinkExtractionResult:
    """从网页提取链接列表

    Args:
        url: 目标页面 URL
        base_url_filter: 可选 URL 前缀过滤（仅返回以此开头的链接）
        limit: 最大返回链接数（1-1000）

    Returns:
        LinkExtractionResult 包含提取的链接列表
    """
    from souwen.web.fetch import validate_fetch_url

    limit = max(1, min(limit, 1000))

    ok, reason = validate_fetch_url(url)
    if not ok:
        return LinkExtractionResult(
            source_url=url,
            error=f"SSRF 校验失败: {reason}",
        )

    try:
        from souwen.scraper.base import BaseScraper

        scraper = BaseScraper(min_delay=0, max_delay=0.1, max_retries=1)
        async with scraper:
            resp = await scraper._fetch(url)

        html = resp.text
        final_url = str(resp.url) if hasattr(resp, "url") else url

        if not html:
            return LinkExtractionResult(
                source_url=url,
                final_url=final_url,
                error="页面内容为空",
            )

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        base_tag = soup.find("base", href=True)
        resolve_base = base_tag["href"] if base_tag else final_url

        seen_urls: set[str] = set()
        links: list[LinkItem] = []
        filtered = 0

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()

            if not href or href.startswith("#"):
                continue

            parsed = urlparse(href)
            if parsed.scheme and parsed.scheme.lower() in _SKIP_SCHEMES:
                continue

            absolute_url = urljoin(resolve_base, href)

            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            ok, _ = validate_fetch_url(absolute_url)
            if not ok:
                filtered += 1
                continue

            if base_url_filter and not absolute_url.startswith(base_url_filter):
                filtered += 1
                continue

            text = a_tag.get_text(separator=" ", strip=True) or ""

            links.append(LinkItem(url=absolute_url, text=text))

            if len(links) >= limit:
                break

        return LinkExtractionResult(
            source_url=url,
            final_url=final_url,
            links=links,
            total=len(links),
            filtered_count=filtered,
        )

    except ImportError:
        return LinkExtractionResult(
            source_url=url,
            error="bs4/lxml 未安装，无法提取链接",
        )
    except Exception as exc:
        logger.warning("链接提取失败: url=%s err=%s", url, exc)
        return LinkExtractionResult(
            source_url=url,
            error=str(exc),
        )
