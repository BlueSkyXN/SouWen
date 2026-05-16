"""Sitemap.xml 解析器

文件用途：
    解析网站的 sitemap.xml（含 sitemap index 和 gzip 压缩），
    提取 URL 列表用于爬虫 seed 或站点审计。
    支持从 robots.txt 自动发现 sitemap 地址。

函数/类清单：
    SitemapEntry(BaseModel)
        - loc: URL 地址
        - lastmod: 最后修改日期
        - changefreq: 更新频率
        - priority: 优先级

    SitemapResult(BaseModel)
        - root_url: 站点根 URL
        - entries: list[SitemapEntry]
        - total: int
        - sitemaps_parsed: int
        - errors: list[str]

    parse_sitemap(url) -> SitemapResult
        - 解析单个 sitemap URL

    discover_sitemap(root_url) -> SitemapResult
        - 从 robots.txt / 常见路径自动发现并解析 sitemap
"""

from __future__ import annotations

import asyncio
import gzip
import logging
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger("souwen.web.sitemap")

# Sitemap index 递归深度限制
_MAX_DEPTH = 3
# 单个 sitemap 最大 URL 数
_MAX_ENTRIES = 50000
# 请求间隔（秒）
_REQUEST_DELAY = 0.5


class SitemapEntry(BaseModel):
    """Sitemap 中的单条 URL 记录"""

    loc: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: float | None = None


class SitemapResult(BaseModel):
    """Sitemap 解析结果"""

    root_url: str
    entries: list[SitemapEntry] = Field(default_factory=list)
    total: int = 0
    sitemaps_parsed: int = 0
    errors: list[str] = Field(default_factory=list)


def _safe_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.strip())
    except (ValueError, TypeError):
        return None


def _parse_sitemap_xml(xml_bytes: bytes) -> tuple[list[SitemapEntry], list[str]]:
    """解析 sitemap XML 内容

    Returns:
        (entries, child_sitemap_urls)
    """
    import defusedxml.ElementTree as ET

    root = ET.fromstring(xml_bytes)

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    entries: list[SitemapEntry] = []
    child_sitemaps: list[str] = []

    for sitemap_tag in root.findall(f"{ns}sitemap"):
        loc = sitemap_tag.findtext(f"{ns}loc")
        if loc:
            child_sitemaps.append(loc.strip())

    for url_tag in root.findall(f"{ns}url"):
        loc = url_tag.findtext(f"{ns}loc")
        if not loc:
            continue
        entries.append(
            SitemapEntry(
                loc=loc.strip(),
                lastmod=url_tag.findtext(f"{ns}lastmod"),
                changefreq=url_tag.findtext(f"{ns}changefreq"),
                priority=_safe_float(url_tag.findtext(f"{ns}priority")),
            )
        )

    return entries, child_sitemaps


async def _fetch_url_bytes(url: str) -> bytes | None:
    """Fetch URL 并返回原始字节内容"""
    try:
        from souwen.core.scraper.base import BaseScraper

        scraper = BaseScraper(min_delay=0, max_delay=0.1, max_retries=1, follow_redirects=True)
        async with scraper:
            resp = await scraper._fetch(url)
            if resp.status_code >= 400:
                return None
            if hasattr(resp, "content") and resp.content:
                return resp.content
            return resp.text.encode("utf-8") if resp.text else None
    except Exception as exc:
        logger.debug("Sitemap fetch failed: %s — %s", url, exc)
        return None


async def parse_sitemap(
    url: str,
    max_entries: int = _MAX_ENTRIES,
) -> SitemapResult:
    """解析单个 sitemap URL

    自动处理 sitemap index 递归和 gzip 压缩。

    Args:
        url: sitemap.xml URL
        max_entries: 最大返回条目数

    Returns:
        SitemapResult
    """
    from souwen.web.fetch import validate_fetch_url

    ok, reason = validate_fetch_url(url)
    if not ok:
        return SitemapResult(root_url=url, errors=[f"SSRF: {reason}"])

    all_entries: list[SitemapEntry] = []
    sitemaps_parsed = 0
    errors: list[str] = []

    queue: list[tuple[str, int]] = [(url, 0)]
    visited: set[str] = set()

    while queue and len(all_entries) < max_entries:
        current_url, depth = queue.pop(0)

        if current_url in visited:
            continue
        visited.add(current_url)

        if depth > _MAX_DEPTH:
            continue

        if sitemaps_parsed > 0:
            await asyncio.sleep(_REQUEST_DELAY)

        raw_bytes = await _fetch_url_bytes(current_url)
        if raw_bytes is None:
            errors.append(f"获取失败: {current_url}")
            continue

        xml_bytes = raw_bytes
        if current_url.endswith(".gz") or raw_bytes[:2] == b"\x1f\x8b":
            try:
                xml_bytes = gzip.decompress(raw_bytes)
            except Exception:
                errors.append(f"gzip 解压失败: {current_url}")
                continue

        try:
            entries, child_sitemaps = _parse_sitemap_xml(xml_bytes)
            sitemaps_parsed += 1

            for entry in entries:
                if len(all_entries) >= max_entries:
                    break
                entry_ok, _ = validate_fetch_url(entry.loc)
                if entry_ok:
                    all_entries.append(entry)

            for child_url in child_sitemaps:
                abs_child = urljoin(current_url, child_url)
                child_ok, _ = validate_fetch_url(abs_child)
                if child_ok and abs_child not in visited:
                    queue.append((abs_child, depth + 1))

        except Exception as exc:
            errors.append(f"XML 解析失败: {current_url} — {exc}")

    return SitemapResult(
        root_url=url,
        entries=all_entries,
        total=len(all_entries),
        sitemaps_parsed=sitemaps_parsed,
        errors=errors,
    )


def _extract_sitemaps_from_robots(robots_text: str, base_url: str) -> list[str]:
    """从 robots.txt 内容中提取 Sitemap 行"""
    sitemaps = []
    for line in robots_text.splitlines():
        line = line.strip()
        if line.lower().startswith("sitemap:"):
            sitemap_url = line.split(":", 1)[1].strip()
            if sitemap_url:
                sitemaps.append(urljoin(base_url, sitemap_url))
    return sitemaps


async def discover_sitemap(
    root_url: str,
    max_entries: int = _MAX_ENTRIES,
) -> SitemapResult:
    """自动发现并解析站点 sitemap

    尝试以下路径（按优先级）：
    1. /robots.txt 中的 Sitemap: 行
    2. /sitemap.xml
    3. /sitemap_index.xml

    Args:
        root_url: 站点根 URL（如 https://example.com）
        max_entries: 最大返回条目数

    Returns:
        SitemapResult
    """
    from souwen.web.fetch import validate_fetch_url

    parsed = urlparse(root_url)
    if not parsed.scheme or not parsed.netloc:
        return SitemapResult(root_url=root_url, errors=["无效 URL: 缺少 scheme/host"])
    origin = f"{parsed.scheme}://{parsed.netloc}"

    ok, reason = validate_fetch_url(origin)
    if not ok:
        return SitemapResult(root_url=root_url, errors=[f"SSRF: {reason}"])

    sitemap_urls: list[str] = []
    robots_url = f"{origin}/robots.txt"
    robots_bytes = await _fetch_url_bytes(robots_url)
    if robots_bytes:
        try:
            robots_text = robots_bytes.decode("utf-8", errors="replace")
            sitemap_urls = _extract_sitemaps_from_robots(robots_text, origin)
        except Exception:
            pass

    if not sitemap_urls:
        for path in ["/sitemap.xml", "/sitemap_index.xml"]:
            sitemap_urls.append(f"{origin}{path}")

    all_entries: list[SitemapEntry] = []
    total_parsed = 0
    all_errors: list[str] = []

    for sitemap_url in sitemap_urls:
        if len(all_entries) >= max_entries:
            break
        result = await parse_sitemap(sitemap_url, max_entries=max_entries - len(all_entries))
        all_entries.extend(result.entries)
        total_parsed += result.sitemaps_parsed
        all_errors.extend(result.errors)

    return SitemapResult(
        root_url=root_url,
        entries=all_entries,
        total=len(all_entries),
        sitemaps_parsed=total_parsed,
        errors=all_errors,
    )
