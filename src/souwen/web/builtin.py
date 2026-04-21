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
    - protego（可选）: robots.txt 解析（启用 respect_robots_txt 时使用）
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from souwen.models import FetchResponse, FetchResult
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.web.builtin")

# 可选依赖探测
_HAS_TRAFILATURA = False
_HAS_HTML2TEXT = False
_HAS_PROTEGO = False

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

try:
    import protego  # noqa: F401

    _HAS_PROTEGO = True
except ImportError:
    pass


# robots.txt 校验使用的固定 User-Agent
_ROBOTS_USER_AGENT = "SouWen/1.0 (+https://github.com/BlueSkyXN/SouWen)"


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
    MAX_REDIRECTS = 5
    MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MiB 响应体大小上限，防 OOM
    _REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

    def __init__(self, respect_robots_txt: bool = False) -> None:
        super().__init__(
            min_delay=0,
            max_delay=0.3,
            max_retries=2,
            follow_redirects=False,
        )
        self.respect_robots_txt = respect_robots_txt
        # robots.txt 缓存：{ "scheme://host[:port]": Protego | None }
        # None 表示该域 robots.txt 拉取失败 / 不存在 → 视为允许
        self._robots_cache: dict[str, Any] = {}

    async def _check_robots(self, url: str) -> tuple[bool, str]:
        """检查目标 URL 是否被该域的 robots.txt 允许

        若 protego 未安装或抓取 robots.txt 失败，按"允许"处理（fail-open）。
        缓存按 scheme+netloc 维度，避免针对同域多 URL 重复抓取。

        Args:
            url: 待检查的 URL

        Returns:
            (allowed, reason)：allowed=False 时 reason 给出拒绝原因
        """
        if not self.respect_robots_txt:
            return True, ""
        if not _HAS_PROTEGO:
            logger.debug("protego 未安装，跳过 robots.txt 检查")
            return True, ""

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True, ""
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._robots_cache:
            robots_url = f"{origin}/robots.txt"
            try:
                resp = await self._fetch(robots_url, headers={"User-Agent": _ROBOTS_USER_AGENT})
                if 200 <= resp.status_code < 300 and resp.text:
                    from protego import Protego

                    self._robots_cache[origin] = Protego.parse(resp.text)
                else:
                    self._robots_cache[origin] = None
            except Exception as exc:  # noqa: BLE001
                logger.debug("robots.txt 抓取失败 %s: %s", robots_url, exc)
                self._robots_cache[origin] = None

        parser = self._robots_cache.get(origin)
        if parser is None:
            return True, ""

        try:
            allowed = parser.can_fetch(url, _ROBOTS_USER_AGENT)
        except Exception as exc:  # noqa: BLE001
            logger.debug("robots.txt 解析异常 %s: %s", url, exc)
            return True, ""

        if not allowed:
            return False, f"robots.txt 拒绝抓取（UA={_ROBOTS_USER_AGENT}）"
        return True, ""

    async def fetch(
        self,
        url: str,
        timeout: float = 30.0,
        start_index: int = 0,
        max_length: int | None = None,
        respect_robots_txt: bool | None = None,
        selector: str | None = None,
    ) -> FetchResult:
        """抓取单个 URL 的内容

        手动跟踪重定向并在每一跳校验 SSRF，防止攻击者通过 302 跳转
        到内部/云元数据地址泄露数据。

        Args:
            url: 目标网页 URL
            timeout: 超时秒数（预留，实际由 BaseScraper 的重试机制控制）
            start_index: 内容起始切片位置（用于分页续读）
            max_length: 内容最大长度，超出则截断并设置 next_start_index
            respect_robots_txt: 覆盖实例级 ``respect_robots_txt`` 设置（仅作用本次调用）
            selector: CSS 选择器，仅提取匹配元素内容（需 bs4 + lxml 支持）

        Returns:
            FetchResult 包含提取的正文内容
        """
        # 临时覆盖实例级配置
        prev_robots = self.respect_robots_txt
        if respect_robots_txt is not None:
            self.respect_robots_txt = respect_robots_txt
        try:
            return await self._fetch_impl(
                url,
                start_index=start_index,
                max_length=max_length,
                selector=selector,
            )
        finally:
            self.respect_robots_txt = prev_robots

    async def _fetch_impl(
        self,
        url: str,
        start_index: int = 0,
        max_length: int | None = None,
        selector: str | None = None,
    ) -> FetchResult:
        try:
            from souwen.web.fetch import validate_fetch_url

            # robots.txt 合规检查（在任何重定向 / 抓取之前）
            allowed, reason = await self._check_robots(url)
            if not allowed:
                logger.info("robots.txt 拒绝: %s (%s)", url, reason)
                return FetchResult(
                    url=url,
                    final_url=url,
                    source=self.PROVIDER_NAME,
                    error=reason,
                    raw={"provider": "builtin", "blocked_by_robots": True},
                )

            # 手动重定向循环 — 每一跳做 SSRF 校验
            current_url = url
            resp = None
            for hop in range(self.MAX_REDIRECTS + 1):
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
                # 超过 MAX_REDIRECTS 仍在跳转
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

            # 大小保护一：响应头声明的 Content-Length
            content_length_header = resp.headers.get("content-length") or resp.headers.get(
                "Content-Length"
            )
            if content_length_header:
                try:
                    declared_size = int(content_length_header)
                except (TypeError, ValueError):
                    declared_size = -1
                if declared_size > self.MAX_RESPONSE_SIZE:
                    logger.warning(
                        "拒绝超大响应 url=%s declared=%d max=%d",
                        url,
                        declared_size,
                        self.MAX_RESPONSE_SIZE,
                    )
                    return FetchResult(
                        url=url,
                        final_url=final_url,
                        source=self.PROVIDER_NAME,
                        error=(
                            f"响应体过大: Content-Length={declared_size} "
                            f"> 上限 {self.MAX_RESPONSE_SIZE}"
                        ),
                        raw={
                            "provider": "builtin",
                            "status_code": resp.status_code,
                            "content_length": declared_size,
                            "oversized": True,
                        },
                    )

            html = resp.text

            # 大小保护二：实际正文长度（防御 Content-Length 缺失或撒谎）
            if html and len(html) > self.MAX_RESPONSE_SIZE:
                logger.warning(
                    "拒绝超大响应 url=%s actual=%d max=%d",
                    url,
                    len(html),
                    self.MAX_RESPONSE_SIZE,
                )
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error=(f"响应体过大: 实际 {len(html)} 字节 > 上限 {self.MAX_RESPONSE_SIZE}"),
                    raw={
                        "provider": "builtin",
                        "status_code": resp.status_code,
                        "content_length": len(html),
                        "oversized": True,
                    },
                )

            if not html or len(html.strip()) < 100:
                return FetchResult(
                    url=url,
                    final_url=final_url,
                    source=self.PROVIDER_NAME,
                    error="页面内容过短或为空",
                    raw={"status_code": resp.status_code, "content_length": len(html)},
                )

            # 提取正文：CSS 选择器优先，否则 trafilatura 全页提取
            selector_matched = False
            if selector:
                try:
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(html, "lxml")
                    selected_elements = soup.select(selector)
                    if selected_elements:
                        selector_matched = True
                        selected_html = "\n".join(str(el) for el in selected_elements)
                        title_text = soup.title.string if soup.title and soup.title.string else ""
                        if _HAS_HTML2TEXT:
                            import html2text

                            h = html2text.HTML2Text()
                            h.ignore_links = False
                            h.ignore_images = True
                            h.body_width = 0
                            extracted = {
                                "content": h.handle(selected_html).strip(),
                                "title": title_text,
                                "author": None,
                                "date": None,
                                "description": "",
                                "content_format": "markdown",
                            }
                        else:
                            extracted = {
                                "content": "\n".join(
                                    el.get_text(separator="\n", strip=True)
                                    for el in selected_elements
                                ),
                                "title": title_text,
                                "author": None,
                                "date": None,
                                "description": "",
                                "content_format": "text",
                            }
                        logger.debug(
                            "CSS selector '%s' matched %d elements",
                            selector,
                            len(selected_elements),
                        )
                    else:
                        logger.info(
                            "CSS selector '%s' matched 0 elements on %s, falling back to full page",
                            selector,
                            url,
                        )
                        extracted = _extract_with_trafilatura(html, url)
                except ImportError:
                    logger.warning("bs4/lxml not installed, ignoring CSS selector")
                    extracted = _extract_with_trafilatura(html, url)
            else:
                extracted = _extract_with_trafilatura(html, url)
            content = extracted["content"]

            # 更好的内容验证：检查长度和词数（基于完整提取结果）
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

            # 分页切片：start_index / max_length
            full_length = len(content)
            sliced = content
            content_truncated = False
            next_start_index: int | None = None

            if start_index < 0:
                start_index = 0
            if start_index >= full_length and full_length > 0:
                sliced = ""
            elif start_index > 0:
                sliced = content[start_index:]

            if max_length is not None and max_length >= 0 and len(sliced) > max_length:
                sliced = sliced[:max_length]
                content_truncated = True
                next_start_index = start_index + max_length

            snippet = sliced[:500] if sliced else ""

            return FetchResult(
                url=url,
                final_url=final_url,
                title=extracted["title"],
                content=sliced,
                content_format=extracted["content_format"],
                content_truncated=content_truncated,
                next_start_index=next_start_index,
                source=self.PROVIDER_NAME,
                snippet=snippet,
                published_date=extracted["date"],
                author=extracted["author"],
                raw={
                    "provider": "builtin",
                    "status_code": resp.status_code,
                    "content_length": len(html),
                    "extracted_length": full_length,
                    "returned_length": len(sliced),
                    "start_index": start_index,
                    "max_length": max_length,
                    "word_count": word_count,
                    "description": extracted.get("description"),
                    "sitename": extracted.get("sitename"),
                    "language": extracted.get("language"),
                    "tags": extracted.get("tags"),
                    "categories": extracted.get("categories"),
                    "has_trafilatura": _HAS_TRAFILATURA,
                    "has_html2text": _HAS_HTML2TEXT,
                    "selector": selector,
                    "selector_matched": selector_matched,
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
