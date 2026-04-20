"""readability-lxml 网页内容抓取客户端

文件用途：
    基于 SouWen 现有 HTTP 基础设施（httpx / curl_cffi）和 readability-lxml 的
    网页内容抓取客户端。继承 BaseScraper 获得 TLS 指纹伪装、WARP 代理、
    自适应退避等反反爬能力，使用 Mozilla Readability 算法提取正文，
    再通过 markdownify / html2text 转换为 Markdown。

    与 builtin（trafilatura）使用的是不同算法 —— Readability 在某些
    博客 / 新闻 / 论坛页面上效果更好，可作为 trafilatura 失败时的备选。
    零外部服务依赖，无需 API Key，支持 WARP 代理加速。

函数/类清单：
    ReadabilityFetcherClient（类）
        - 功能：使用 Readability 算法的网页抓取客户端
        - 继承：BaseScraper（爬虫基类，提供 TLS 指纹 / WARP / 退避）
        - 关键属性：
            ENGINE_NAME   = "readability"
            PROVIDER_NAME = "readability"
        - 主要方法：
            * fetch(url) → FetchResult
            * fetch_batch(urls, max_concurrency, timeout) → FetchResponse

    _extract_with_readability(html, url) → dict
        - 功能：在线程池中调用同步的 Readability + markdownify 完成提取
        - 回退：markdownify 缺失时使用 html2text；再缺失则降级 _html_extract

模块依赖：
    - asyncio: 异步并发与 to_thread 转同步
    - logging: 日志记录
    - souwen.exceptions: ConfigError（依赖缺失时抛出）
    - souwen.scraper.base: BaseScraper 基类
    - souwen.models: FetchResult, FetchResponse 数据模型
    - readability-lxml（必需）: Mozilla Readability HTML 正文提取
    - markdownify（可选）: HTML→Markdown 首选方案
    - html2text（可选）: HTML→Markdown 回退方案
    - souwen.web._html_extract: 最终回退方案

技术要点：
    - readability-lxml 仅做正文提取，HTTP 抓取仍走 BaseScraper
      （获得 TLS 指纹伪装、WARP 代理、自适应退避等能力）
    - readability.Document 是同步阻塞调用，使用 asyncio.to_thread 移出事件循环
    - 手动跟踪重定向并在每跳做 SSRF 校验（与 builtin 一致）
    - 内容质量校验：长度 ≥ 50 字符、词数 ≥ 10（CJK aware）
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin

from souwen.exceptions import ConfigError
from souwen.models import FetchResponse, FetchResult
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.readability")


_HAS_READABILITY = False
_HAS_MARKDOWNIFY = False
_HAS_HTML2TEXT = False

try:
    from readability import Document  # type: ignore[import-not-found]

    _HAS_READABILITY = True
except ImportError:
    pass

try:
    from markdownify import markdownify as _markdownify  # type: ignore[import-not-found]

    _HAS_MARKDOWNIFY = True
except ImportError:
    pass

try:
    import html2text as _html2text_mod  # noqa: F401

    _HAS_HTML2TEXT = True
except ImportError:
    pass


_CJK_PATTERN = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7af]"


def _count_words(text: str) -> int:
    """CJK-aware 词数统计（CJK 字符按字计数）"""
    cjk_chars = len(re.findall(_CJK_PATTERN, text))
    non_cjk = re.sub(_CJK_PATTERN, " ", text)
    latin_words = len(non_cjk.split())
    return cjk_chars + latin_words


def _html_to_markdown(article_html: str) -> tuple[str, str]:
    """将 Readability 提取出的 HTML 片段转换为 Markdown

    优先级：markdownify > html2text > 正则剥离纯文本

    Returns:
        (content, content_format) — content_format 为 "markdown" 或 "text"
    """
    if _HAS_MARKDOWNIFY:
        md = _markdownify(article_html, heading_style="ATX")
        if md and md.strip():
            return md.strip(), "markdown"

    if _HAS_HTML2TEXT:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        md = h.handle(article_html)
        if md and md.strip():
            return md.strip(), "markdown"

    # 最终回退：正则剥离 HTML 标签
    text = re.sub(r"<script[^>]*>.*?</script>", "", article_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text, "text"


def _extract_with_readability_sync(html: str, url: str) -> dict[str, Any]:
    """同步执行 Readability 提取 + Markdown 转换

    在线程池中调用以避免阻塞事件循环。

    Args:
        html: 原始 HTML
        url: 源 URL（用于日志）

    Returns:
        包含 content, title, content_format 的字典；
        失败时回退到 _html_extract.extract_from_html。
    """
    if _HAS_READABILITY:
        try:
            doc = Document(html)
            title = doc.title() or ""
            article_html = doc.summary() or ""
            if article_html.strip():
                content, content_format = _html_to_markdown(article_html)
                if content:
                    return {
                        "content": content,
                        "title": title,
                        "content_format": content_format,
                    }
        except Exception as exc:
            logger.debug("Readability 提取失败 url=%s err=%s", url, exc)

    # 回退到 _html_extract（trafilatura/html2text/正则）
    from souwen.web._html_extract import extract_from_html

    fallback = extract_from_html(html, url)
    return {
        "content": fallback.get("content", "") or "",
        "title": fallback.get("title", "") or "",
        "content_format": fallback.get("content_format", "text"),
    }


class ReadabilityFetcherClient(BaseScraper):
    """基于 Mozilla Readability 算法的网页抓取客户端

    使用 SouWen 自有的 HTTP 栈（httpx / curl_cffi + TLS 指纹 + WARP）抓取网页，
    用 readability-lxml 提取正文，markdownify / html2text 转 Markdown。

    适用场景：
    - trafilatura 在某些页面上失败时的备选算法
    - 偏向博客 / 新闻 / 论坛形态页面的内容提取
    """

    ENGINE_NAME = "readability"
    PROVIDER_NAME = "readability"
    MAX_REDIRECTS = 5
    _REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

    def __init__(self) -> None:
        if not _HAS_READABILITY:
            raise ConfigError(
                "readability-lxml",
                "Readability Fetcher",
                "https://pypi.org/project/readability-lxml/",
            )
        super().__init__(
            min_delay=0,
            max_delay=0.3,
            max_retries=2,
            follow_redirects=False,
        )

    async def __aenter__(self) -> "ReadabilityFetcherClient":
        await super().__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await super().__aexit__(*args)

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 的内容

        手动跟踪重定向并在每一跳校验 SSRF，防止攻击者通过 302 跳转
        到内部/云元数据地址泄露数据。

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（预留，实际由 BaseScraper 重试机制控制）

        Returns:
            FetchResult 包含提取的正文内容
        """
        try:
            from souwen.web.fetch import validate_fetch_url

            current_url = url
            resp = None
            for _hop in range(self.MAX_REDIRECTS + 1):
                resp = await self._fetch(current_url)

                if resp.status_code not in self._REDIRECT_CODES:
                    break

                location = resp.headers.get("location")
                if not location:
                    break

                redirect_url = urljoin(current_url, location)
                ok, reason = validate_fetch_url(redirect_url)
                if not ok:
                    logger.warning(
                        "SSRF redirect blocked: %s → %s (%s)",
                        url,
                        redirect_url,
                        reason,
                    )
                    return FetchResult(
                        url=url,
                        final_url=redirect_url,
                        source=self.PROVIDER_NAME,
                        error=f"SSRF: 重定向目标被拦截 ({reason})",
                    )
                current_url = redirect_url
            else:
                return FetchResult(
                    url=url,
                    final_url=current_url,
                    source=self.PROVIDER_NAME,
                    error=f"重定向次数超过上限 ({self.MAX_REDIRECTS})",
                )

            if resp is None:
                return FetchResult(
                    url=url,
                    final_url=url,
                    source=self.PROVIDER_NAME,
                    error="请求失败",
                )

            final_url = current_url
            html = resp.text

            if not html or len(html.strip()) < 100:
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error="页面内容过短或为空",
                    raw={"status_code": resp.status_code, "content_length": len(html)},
                )

            # Readability 是同步阻塞调用，移出事件循环
            extracted = await asyncio.to_thread(_extract_with_readability_sync, html, url)
            content = extracted["content"]

            MIN_CONTENT_LENGTH = 50
            MIN_WORD_COUNT = 10
            word_count = _count_words(content) if content else 0

            if not content or len(content) < MIN_CONTENT_LENGTH or word_count < MIN_WORD_COUNT:
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error=f"提取内容过短 (长度:{len(content) if content else 0}, 词数:{word_count})",
                    raw={
                        "status_code": resp.status_code,
                        "content_length": len(html),
                        "extracted_length": len(content) if content else 0,
                        "word_count": word_count,
                    },
                )

            snippet = content[:500] if content else ""

            return FetchResult(
                url=url,
                final_url=final_url,
                title=extracted["title"],
                content=content,
                content_format=extracted["content_format"],
                source=self.PROVIDER_NAME,
                snippet=snippet,
                raw={
                    "provider": "readability",
                    "status_code": resp.status_code,
                    "content_length": len(html),
                    "extracted_length": len(content),
                    "word_count": word_count,
                    "has_readability": _HAS_READABILITY,
                    "has_markdownify": _HAS_MARKDOWNIFY,
                    "has_html2text": _HAS_HTML2TEXT,
                },
            )

        except Exception as exc:
            logger.warning("Readability fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "readability"},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 3,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数
            timeout: 单 URL 超时

        Returns:
            FetchResponse 聚合结果
        """
        sem = asyncio.Semaphore(max_concurrency)

        async def _fetch_one(u: str) -> FetchResult:
            async with sem:
                return await self.fetch(u, timeout=timeout)

        results = await asyncio.gather(*[_fetch_one(u) for u in urls])
        result_list = list(results)
        ok = sum(1 for r in result_list if r.error is None)
        return FetchResponse(
            urls=urls,
            results=result_list,
            total=len(result_list),
            total_ok=ok,
            total_failed=len(result_list) - ok,
            provider=self.PROVIDER_NAME,
        )
