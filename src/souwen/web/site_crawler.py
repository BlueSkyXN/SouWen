"""多页面 BFS 站点爬虫

文件用途：
    以 deepwiki-mcp 的 httpCrawler.ts 为参考，使用 Python asyncio + httpx
    实现广度优先（BFS）站点爬虫。从根 URL 出发，限制在同域内按深度爬取，
    将每页 HTML 转换为 Markdown 并聚合输出。

    核心设计参照来源：
        https://github.com/regenrek/deepwiki-mcp/blob/main/src/lib/httpCrawler.ts

函数/类清单：
    _NON_HTML_EXTS（frozenset）
        - 非 HTML 文件扩展名集合，命中时跳过

    _extract_links(html, base_url) -> list[str]
        - 从 HTML 中提取同域链接（正则 + URL 归一化）

    _html_to_markdown(html, url) -> str
        - HTML → Markdown 转换（trafilatura 优先，html2text 回退，纯文本最终回退）

    SiteCrawlerClient（类）
        - 功能：多页面 BFS 站点爬虫客户端
        - 关键属性：
            PROVIDER_NAME = "site_crawler"
        - 主要方法：
            * crawl(root_url, max_depth, max_concurrency, timeout, mode) → FetchResponse
            * fetch_batch(urls, ...) → FetchResponse（单 URL 兼容接口）

    crawl_site(root_url, ...) → FetchResponse
        - 模块级便捷函数（async）

模块依赖：
    - asyncio: 并发控制（Semaphore / Queue）
    - re: 链接提取正则
    - time: 性能计时
    - logging: 日志记录
    - httpx: 异步 HTTP 请求
    - souwen.models: FetchResult, FetchResponse 数据模型
    - trafilatura（可选）: HTML → Markdown 高质量转换
    - html2text（可选）: HTML → Markdown 回退
    - protego（可选）: robots.txt 解析

技术要点：
    - BFS：asyncio.Queue + asyncio.Semaphore（并发限制）
    - 域安全：仅爬取与根 URL 同 hostname 的页面
    - 深度限制：每个 URL 附带深度计数器，超限跳过
    - robots.txt：protego 可选解析，失败时 fail-open
    - 重试：指数退避（BACKOFF_BASE_MS × 2^retry）
    - Content-Type 检查：非 text/html 响应直接跳过
    - 扩展名过滤：与 deepwiki-mcp 保持一致
    - 聚合模式（aggregate）：全部页面合并为单个 Markdown
    - 分页模式（pages）：每页独立 FetchResult
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Literal
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from souwen.models import FetchResponse, FetchResult

logger = logging.getLogger("souwen.web.site_crawler")

# 与 deepwiki-mcp httpCrawler.ts 保持一致的非 HTML 扩展名集合
_NON_HTML_EXTS: frozenset[str] = frozenset(
    {
        ".css",
        ".js",
        ".mjs",
        ".json",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".mp4",
        ".mp3",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".m4a",
        ".ogg",
        ".wav",
        ".bmp",
        ".tiff",
        ".psd",
        ".exe",
        ".dmg",
        ".apk",
        ".bin",
        ".7z",
        ".rar",
        ".xml",
        ".rss",
        ".atom",
        ".map",
        ".txt",
        ".csv",
        ".md",
        ".yml",
        ".yaml",
        ".log",
        ".rtf",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
        ".xls",
        ".xlsx",
        ".db",
        ".sqlite",
        ".swf",
        ".dat",
    }
)

# 内置 User-Agent（礼貌标识）
_USER_AGENT = "SouWen-SiteCrawler/1.0 (+https://github.com/BlueSkyXN/SouWen)"

# 重试参数（对齐 deepwiki-mcp RETRY_LIMIT / BACKOFF_BASE_MS）
_RETRY_LIMIT = 3
_BACKOFF_BASE_S = 0.25  # 250ms

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


def _normalize_url(url: str) -> str:
    """去除 fragment，统一去尾部斜杠（根路径保留）以便去重"""
    parsed = urlparse(url)
    # 去除 fragment
    clean = urlunparse(parsed._replace(fragment=""))
    # 根路径 "/" 保留，其他路径去尾斜杠
    if clean.endswith("/") and urlparse(clean).path != "/":
        clean = clean.rstrip("/")
    return clean


def _is_html_path(path: str) -> bool:
    """判断路径扩展名是否非 HTML（快速过滤）"""
    lower = path.lower().split("?")[0]
    for ext in _NON_HTML_EXTS:
        if lower.endswith(ext):
            return False
    return True


def _extract_links(html: str, base_url: str) -> list[str]:
    """从 HTML 中提取绝对链接（同域内有效 URL）

    使用正则提取 href 属性（与 deepwiki-mcp 保持一致的朴素策略），
    然后通过 urljoin 归一化为绝对 URL。

    Args:
        html: 原始 HTML 字符串
        base_url: 当前页面 URL（用于解析相对链接）

    Returns:
        绝对 URL 列表（未去重，由调用方决定）
    """
    links: list[str] = []
    # 匹配 href="..." 或 href='...'（[^"'#\s]+ 已排除 fragment，无需额外后缀）
    pattern = re.compile(r"""href=["']([^"'#\s]+)["']""", re.IGNORECASE)
    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        if not raw or raw.startswith("javascript:") or raw.startswith("mailto:"):
            continue
        try:
            abs_url = urljoin(base_url, raw)
            links.append(abs_url)
        except Exception:
            pass
    return links


def _html_to_markdown(html: str, url: str = "") -> str:
    """HTML → Markdown 转换（trafilatura → html2text → 纯文本）

    优先级：
    1. trafilatura（高质量，支持正文提取）
    2. html2text（通用 HTML→MD）
    3. 正则去标签（最终回退）

    Args:
        html: 原始 HTML
        url: 页面 URL（trafilatura 元数据推断用）

    Returns:
        Markdown / 纯文本内容
    """
    if _HAS_TRAFILATURA:
        import trafilatura

        content = trafilatura.extract(
            html,
            url=url or None,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            include_formatting=True,
            favor_precision=False,  # 文档站点内容更宽松
            deduplicate=True,
            with_metadata=False,
        )
        if content:
            return content

    if _HAS_HTML2TEXT:
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        md = h.handle(html)
        if md.strip():
            return md.strip()

    # 最终回退：正则剥标签
    text = re.sub(r"<script[^>]*>.*?</\s*script[^>]*>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</\s*style[^>]*>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SiteCrawlerClient:
    """多页面 BFS 站点爬虫

    从根 URL 出发，广度优先爬取同域内所有页面，将每页转换为 Markdown。
    参照 deepwiki-mcp 的 httpCrawler.ts 逻辑，使用 Python asyncio 实现。

    特性：
    - BFS 深度控制（max_depth）
    - 并发限制（asyncio.Semaphore）
    - 重试指数退避
    - robots.txt 遵守（可选，需 protego）
    - Content-Type 过滤（非 text/html 跳过）
    - 非 HTML 扩展名快速跳过
    - 两种输出模式：aggregate（聚合单文档）/ pages（每页独立）

    Args:
        respect_robots_txt: 是否遵守 robots.txt（需安装 protego，默认 True）
        user_agent: 请求 User-Agent（默认 SouWen-SiteCrawler）
    """

    PROVIDER_NAME = "site_crawler"

    def __init__(
        self,
        respect_robots_txt: bool = True,
        user_agent: str = _USER_AGENT,
    ) -> None:
        self.respect_robots_txt = respect_robots_txt
        self.user_agent = user_agent
        # robots.txt 缓存：{origin: protego.Protego | None}
        self._robots_cache: dict[str, object] = {}

    # ------------------------------------------------------------------
    # robots.txt 支持
    # ------------------------------------------------------------------

    async def _fetch_robots(self, client: httpx.AsyncClient, origin: str) -> object | None:
        """获取并解析域的 robots.txt（fail-open：失败返回 None 视为允许）"""
        if not self.respect_robots_txt or not _HAS_PROTEGO:
            return None
        if origin in self._robots_cache:
            return self._robots_cache[origin]
        try:
            resp = await client.get(f"{origin}/robots.txt", timeout=10.0)
            if resp.status_code == 200:
                import protego

                robots = protego.Protego.parse(resp.text)
            else:
                robots = None
        except Exception:
            robots = None
        self._robots_cache[origin] = robots
        return robots

    def _robots_allowed(self, robots: object | None, url: str) -> bool:
        """检查 URL 是否被 robots.txt 允许（fail-open）"""
        if robots is None:
            return True
        try:
            # robots is a protego.Protego instance when not None;
            # use getattr to avoid a hard import of the optional dependency.
            can_fetch = getattr(robots, "can_fetch", None)
            if callable(can_fetch):
                return bool(can_fetch(url, self.user_agent))
            return True
        except Exception:
            return True

    # ------------------------------------------------------------------
    # 核心爬取
    # ------------------------------------------------------------------

    async def crawl(
        self,
        root_url: str,
        max_depth: int = 1,
        max_concurrency: int = 5,
        timeout: float = 30.0,
        mode: Literal["aggregate", "pages"] = "aggregate",
        allowed_domain: str | None = None,
    ) -> FetchResponse:
        """BFS 爬取整个站点

        从 root_url 出发广度优先爬取，深度不超过 max_depth，
        仅爬取与 root_url 同域（或 allowed_domain 指定域）的页面。

        Args:
            root_url: 爬取起点 URL
            max_depth: 最大爬取深度（0 = 仅根页面，1 = 根 + 一级子页面）
            max_concurrency: 最大并发请求数
            timeout: 单次请求超时秒数
            mode: 输出模式 — "aggregate" 合并单文档 / "pages" 每页独立
            allowed_domain: 仅允许爬取的域名（默认与 root_url 同域）

        Returns:
            FetchResponse，results 为每页 FetchResult（pages 模式）
            或单个聚合 FetchResult（aggregate 模式）
        """
        t0 = time.perf_counter()
        parsed_root = urlparse(root_url)
        root_hostname = parsed_root.hostname or ""
        origin = f"{parsed_root.scheme}://{parsed_root.netloc}"
        allowed_host = allowed_domain or root_hostname

        # 去重集合、BFS 队列、结果容器
        visited: set[str] = set()
        # queue items: (url, depth)
        queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        sem = asyncio.Semaphore(max_concurrency)

        page_results: dict[str, str] = {}  # path → markdown
        errors: list[tuple[str, str]] = []  # (url, reason)

        normalized_root = _normalize_url(root_url)
        visited.add(normalized_root)
        await queue.put((root_url, 0))

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
        ) as client:
            # 预取 robots.txt
            robots = await self._fetch_robots(client, origin)

            async def fetch_one(url: str, depth: int) -> None:
                """单页抓取任务（含重试，最多 _RETRY_LIMIT 次）"""
                html: str | None = None
                async with sem:
                    for attempt in range(_RETRY_LIMIT):
                        try:
                            resp = await client.get(url, timeout=timeout)
                            ct = resp.headers.get("content-type", "")
                            if "text/html" not in ct:
                                return
                            html = resp.text
                            break
                        except Exception as exc:
                            if attempt < _RETRY_LIMIT - 1:
                                backoff = _BACKOFF_BASE_S * (2**attempt)
                                await asyncio.sleep(backoff)
                            else:
                                errors.append((url, str(exc)))
                                return

                if html is None:
                    return

                # HTML → Markdown
                md = _html_to_markdown(html, url)
                path = urlparse(url).path or "/"
                page_results[path] = md

                # 提取子链接（深度未超限时）
                if depth < max_depth:
                    for child_url in _extract_links(html, url):
                        child_norm = _normalize_url(child_url)
                        child_parsed = urlparse(child_url)
                        # 域过滤
                        if child_parsed.hostname != allowed_host:
                            continue
                        # 扩展名过滤
                        if not _is_html_path(child_parsed.path):
                            continue
                        # 路径为 /robots.txt 跳过
                        if child_parsed.path == "/robots.txt":
                            continue
                        # 去重
                        if child_norm in visited:
                            continue
                        # robots.txt 检查
                        if not self._robots_allowed(robots, child_url):
                            continue
                        visited.add(child_norm)
                        await queue.put((child_url, depth + 1))

            # 持续消费队列直到为空
            tasks: list[asyncio.Task] = []
            while not queue.empty() or tasks:
                # 批量启动队列中的任务
                while not queue.empty():
                    url, depth = await queue.get()
                    task = asyncio.create_task(fetch_one(url, depth))
                    tasks.append(task)

                # 等待至少一个任务完成（避免 CPU 忙轮询）
                if tasks:
                    done, tasks_set = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(tasks_set)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        total_bytes = sum(len(md.encode()) for md in page_results.values())

        # 构建 FetchResult 列表
        results: list[FetchResult] = []

        if mode == "pages":
            for path, md in sorted(page_results.items()):
                page_url = f"{origin}{path}"
                results.append(
                    FetchResult(
                        url=page_url,
                        final_url=page_url,
                        title=path,
                        content=md,
                        content_format="markdown",
                        source=self.PROVIDER_NAME,
                        snippet=md[:500],
                        raw={
                            "provider": self.PROVIDER_NAME,
                            "mode": "pages",
                            "elapsed_ms": elapsed_ms,
                        },
                    )
                )
        else:
            # aggregate：按路径排序后拼接
            parts: list[str] = []
            for path, md in sorted(page_results.items()):
                parts.append(f"# {path}\n\n{md}")
            aggregated = "\n\n---\n\n".join(parts)
            results.append(
                FetchResult(
                    url=root_url,
                    final_url=root_url,
                    title=root_url,
                    content=aggregated,
                    content_format="markdown",
                    source=self.PROVIDER_NAME,
                    snippet=aggregated[:500],
                    raw={
                        "provider": self.PROVIDER_NAME,
                        "mode": "aggregate",
                        "total_pages": len(page_results),
                        "total_bytes": total_bytes,
                        "elapsed_ms": elapsed_ms,
                        "errors": [{"url": u, "reason": r} for u, r in errors],
                    },
                )
            )

        # 错误条目（仅 pages 模式追加）
        if mode == "pages":
            for err_url, reason in errors:
                results.append(
                    FetchResult(
                        url=err_url,
                        final_url=err_url,
                        source=self.PROVIDER_NAME,
                        error=reason,
                        raw={"provider": self.PROVIDER_NAME},
                    )
                )

        ok_count = sum(1 for r in results if not r.error)
        fail_count = sum(1 for r in results if r.error)

        logger.info(
            "SiteCrawler 完成: root=%s pages=%d errors=%d elapsed=%dms",
            root_url,
            len(page_results),
            len(errors),
            elapsed_ms,
        )

        return FetchResponse(
            urls=[root_url],
            results=results,
            total=len(results),
            total_ok=ok_count,
            total_failed=fail_count,
            provider=self.PROVIDER_NAME,
            meta={
                "root_url": root_url,
                "max_depth": max_depth,
                "mode": mode,
                "total_pages_crawled": len(page_results),
                "total_errors": len(errors),
                "elapsed_ms": elapsed_ms,
            },
        )

    async def fetch_batch(
        self,
        urls: list[str],
        max_concurrency: int = 5,
        timeout: float = 30.0,
        max_depth: int = 0,
        mode: Literal["aggregate", "pages"] = "aggregate",
    ) -> FetchResponse:
        """对 URL 列表每个独立执行 crawl（兼容通用 fetch_batch 接口）

        Args:
            urls: URL 列表（每个独立爬取，max_depth=0 即单页模式）
            max_concurrency: 并发数
            timeout: 超时
            max_depth: 每个 URL 的爬取深度（默认 0 = 仅当前页）
            mode: 聚合模式

        Returns:
            FetchResponse（所有 URL 结果合并）
        """
        all_results: list[FetchResult] = []
        for url in urls:
            resp = await self.crawl(
                url,
                max_depth=max_depth,
                max_concurrency=max_concurrency,
                timeout=timeout,
                mode=mode,
            )
            all_results.extend(resp.results)

        ok_count = sum(1 for r in all_results if not r.error)
        fail_count = sum(1 for r in all_results if r.error)
        return FetchResponse(
            urls=urls,
            results=all_results,
            total=len(all_results),
            total_ok=ok_count,
            total_failed=fail_count,
            provider=self.PROVIDER_NAME,
        )

    # ------------------------------------------------------------------
    # 上下文管理器（与其他 SouWen 客户端接口一致）
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "SiteCrawlerClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


async def crawl_site(
    root_url: str,
    max_depth: int = 1,
    max_concurrency: int = 5,
    timeout: float = 30.0,
    mode: Literal["aggregate", "pages"] = "aggregate",
    respect_robots_txt: bool = True,
) -> FetchResponse:
    """便捷异步函数：爬取站点并返回 FetchResponse

    Args:
        root_url: 爬取起点 URL
        max_depth: 最大深度（0 = 仅根页面）
        max_concurrency: 并发数
        timeout: 超时秒数
        mode: 输出模式（aggregate / pages）
        respect_robots_txt: 是否遵守 robots.txt

    Returns:
        FetchResponse
    """
    async with SiteCrawlerClient(respect_robots_txt=respect_robots_txt) as crawler:
        return await crawler.crawl(
            root_url,
            max_depth=max_depth,
            max_concurrency=max_concurrency,
            timeout=timeout,
            mode=mode,
        )
