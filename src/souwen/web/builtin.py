"""内置网页内容抓取客户端

文件用途：
    基于 SouWen 现有 HTTP 基础设施（httpx / curl_cffi）和 trafilatura 的内置
    网页内容抓取客户端。继承 BaseScraper 获得 TLS 指纹伪装、WARP 代理、
    自适应退避等反反爬能力，使用 trafilatura 提取正文并转换为 Markdown。

    零外部服务依赖，无需 API Key，支持 WARP 代理加速。

函数/类清单：
    BuiltinFetcherClient（类）
        - 功能：内置网页内容抓取客户端
        - 继承：BaseScraper（爬虫基类，提供 TLS 指纹 / WARP / 退避）
        - 关键属性：
            ENGINE_NAME   = "builtin_fetch"
            PROVIDER_NAME = "builtin"
        - 主要方法：
            * fetch(url) → FetchResult
            * fetch_batch(urls, max_concurrency, timeout) → FetchResponse

    _extract_with_trafilatura(html, url) → dict
        - 功能：使用 trafilatura 提取正文、标题、作者、日期等元数据
        - 回退：trafilatura 失败时降级到 html2text / 纯文本

    _extract_fallback(html) → str
        - 功能：trafilatura 不可用时的简单 HTML→text 提取

模块依赖：
    - asyncio: 并发控制
    - logging: 日志记录
    - souwen.scraper.base: BaseScraper 基类
    - souwen.models: FetchResult, FetchResponse 数据模型
    - trafilatura（可选）: HTML 正文提取 + Markdown 转换
    - html2text（可选）: HTML→Markdown 回退方案
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from souwen.models import FetchResponse, FetchResult
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.builtin")

# 可选依赖探测
_HAS_TRAFILATURA = False
_HAS_HTML2TEXT = False

try:
    import trafilatura  # noqa: F401

    _HAS_TRAFILATURA = True
except ImportError:
    pass

try:
    import html2text as _html2text_mod  # noqa: F401

    _HAS_HTML2TEXT = True
except ImportError:
    pass


_CJK_PATTERN = r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\u31f0-\u31ff\uac00-\ud7af]"


def _count_words(text: str) -> int:
    """CJK-aware word count. CJK characters count as individual words."""
    cjk_chars = len(re.findall(_CJK_PATTERN, text))
    non_cjk = re.sub(_CJK_PATTERN, " ", text)
    latin_words = len(non_cjk.split())
    return cjk_chars + latin_words


def _extract_fallback(html: str) -> str:
    """简单 HTML→text 回退（无外部依赖）

    去除 HTML 标签，保留纯文本。用于 trafilatura 和 html2text 都不可用时。
    """
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_with_trafilatura(html: str, url: str) -> dict[str, Any]:
    """使用 trafilatura 提取正文和元数据

    Args:
        html: 原始 HTML 字符串
        url: 源 URL（用于元数据推断）

    Returns:
        包含 content, title, author, date, description, language, sitename, images 等的字典
    """
    if _HAS_TRAFILATURA:
        import trafilatura

        # 使用 trafilatura 原生 markdown 输出（业界最佳实践）
        content = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
            include_formatting=True,
            favor_precision=True,
            deduplicate=True,
            with_metadata=False,
        )

        # 提取完整元数据
        metadata = trafilatura.extract_metadata(html, default_url=url)

        if content:
            return {
                "content": content,
                "title": (metadata.title if metadata else "") or "",
                "author": metadata.author if metadata else None,
                "date": metadata.date if metadata else None,
                "description": (metadata.description if metadata else "") or "",
                "sitename": metadata.sitename if metadata else None,
                "language": metadata.language if metadata else None,
                "tags": metadata.tags if metadata else None,
                "categories": metadata.categories if metadata else None,
                "content_format": "markdown",
            }

        # 如果 extract 失败，尝试 bare_extraction
        # bare_extraction 返回 Document 对象（非 dict），需用属性访问
        result = trafilatura.bare_extraction(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=True,
            include_tables=True,
            favor_precision=True,
        )
        if result and getattr(result, "text", None):
            return {
                "content": result.text,
                "title": getattr(result, "title", "") or "",
                "author": getattr(result, "author", None),
                "date": getattr(result, "date", None),
                "description": getattr(result, "description", "") or "",
                "sitename": getattr(result, "sitename", None),
                "language": getattr(result, "language", None),
                "content_format": "markdown",
            }

    # 回退到 html2text
    if _HAS_HTML2TEXT:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        md = h.handle(html)
        if md.strip():
            return {
                "content": md.strip(),
                "title": "",
                "author": None,
                "date": None,
                "description": "",
                "content_format": "markdown",
            }

    # 最终回退：纯正则剥离
    text = _extract_fallback(html)
    return {
        "content": text,
        "title": "",
        "author": None,
        "date": None,
        "description": "",
        "content_format": "text",
    }


class BuiltinFetcherClient(BaseScraper):
    """内置网页内容抓取客户端

    使用 SouWen 自有的 HTTP 栈（httpx / curl_cffi + TLS 指纹 + WARP）
    抓取网页，用 trafilatura 提取正文。无需任何第三方 API Key。

    特性：
    - curl_cffi TLS 指纹伪装（Chrome JA3）
    - WARP 代理支持
    - trafilatura 正文提取 + Markdown/text 输出
    - 自适应退避（429 限流感知）
    """

    ENGINE_NAME = "builtin_fetch"
    PROVIDER_NAME = "builtin"

    def __init__(self) -> None:
        super().__init__(
            min_delay=0,
            max_delay=0.3,
            max_retries=2,
        )

    async def fetch(self, url: str, timeout: float = 30.0) -> FetchResult:
        """抓取单个 URL 的内容

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（预留，实际由 BaseScraper 的重试机制控制）

        Returns:
            FetchResult 包含提取的正文内容
        """
        try:
            resp = await self._fetch(url)
            html = resp.text
            final_url = str(resp.url) if hasattr(resp, "url") else url

            if not html or len(html.strip()) < 100:
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error="页面内容过短或为空",
                    raw={"status_code": resp.status_code, "content_length": len(html)},
                )

            # 提取正文
            extracted = _extract_with_trafilatura(html, url)
            content = extracted["content"]

            # 更好的内容验证：检查长度和词数
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
                published_date=extracted["date"],
                author=extracted["author"],
                raw={
                    "provider": "builtin",
                    "status_code": resp.status_code,
                    "content_length": len(html),
                    "extracted_length": len(content),
                    "word_count": word_count,
                    "description": extracted.get("description"),
                    "sitename": extracted.get("sitename"),
                    "language": extracted.get("language"),
                    "tags": extracted.get("tags"),
                    "categories": extracted.get("categories"),
                    "has_trafilatura": _HAS_TRAFILATURA,
                    "has_html2text": _HAS_HTML2TEXT,
                },
            )

        except Exception as exc:
            logger.warning("Builtin fetch failed: url=%s err=%s", url, exc)
            return FetchResult(
                url=url,
                final_url=url,
                source=self.PROVIDER_NAME,
                error=str(exc),
                raw={"provider": "builtin"},
            )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 5,
        timeout: float = 30.0,
    ) -> FetchResponse:
        """批量抓取多个 URL

        Args:
            urls: URL 列表
            max_concurrency: 最大并发数
            timeout: 每个 URL 超时

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
