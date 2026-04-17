"""Google Patents 爬虫客户端 (兜底方案)

Google Patents 无官方 API，采用爬虫方式获取数据。
优先使用 httpx + BeautifulSoup 静态解析；
如遇 JS 渲染页面，可选用 Playwright 动态渲染。

⚠️ 本模块为兜底方案，建议优先使用官方 API 数据源。

文件用途：
    Google Patents 爬虫客户端，通过网页抓取获取专利数据。
    支持两种抓取策略：静态解析（快速）和动态渲染（准确）。
    集成 Playwright 浏览器池，复用单个浏览器实例以优化资源。

函数/类清单：
    GooglePatentsClient（类）
        - 功能：Google Patents 网页爬虫客户端
        - 关键属性：BASE_URL (str) Google Patents 网站地址，_use_playwright (bool) 是否启用动态渲染
        - 关键变量：_http (SouWenHttpClient) HTTP 客户端，_limiter 速率限制器
    
    search(query: str, num_results: int = 10) -> SearchResponse
        - 功能：搜索 Google Patents
        - 输入：query 搜索关键词，num_results 期望返回数量
        - 输出：SearchResponse 包含搜索结果
    
    get_patent(patent_id: str) -> PatentResult
        - 功能：获取专利详情页面数据
        - 输入：patent_id 专利号（如 US11234567B2）
        - 输出：PatentResult 专利详情
        - 异常：NotFoundError 专利不可用时抛出
    
    _search_static(query: str, num_results: int) -> list[PatentResult]
        - 功能：使用 httpx + BeautifulSoup 静态解析搜索结果
        - 返回可能为空列表（若 BeautifulSoup 不可用或解析失败）
    
    _parse_search_page(soup: Any) -> list[PatentResult]（静态方法）
        - 功能：解析搜索结果 HTML，提取专利列表
    
    _parse_detail_page(soup: Any, patent_id: str) -> PatentResult | None（静态方法）
        - 功能：解析专利详情 HTML 页面
    
    _search_playwright(query: str, num_results: int) -> list[PatentResult]
        - 功能：使用 Playwright 动态渲染搜索结果（兜底策略）
    
    _get_patent_playwright(patent_id: str) -> PatentResult | None
        - 功能：使用 Playwright 动态渲染专利详情（兜底策略）

    _BrowserPool（类）
        - 功能：Playwright 浏览器实例池，模块级单例
        - 特点：复用单个 Chromium 实例，每次请求创建独立 BrowserContext

模块依赖：
    - httpx: HTTP 异步客户端
    - beautifulsoup4: HTML 解析（可选但推荐）
    - playwright: 动态渲染引擎（可选）
    - souwen._parsing: 安全日期解析
    - souwen.models: 统一数据模型
    - souwen.rate_limiter: 限流控制
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import random
from typing import Any

from souwen._parsing import safe_parse_date
from souwen.exceptions import NotFoundError
from souwen.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

# 随机 User-Agent 池（保持多样性，定期更新版本号）
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
]


def _random_ua() -> str:
    """返回随机 User-Agent，降低被反爬识别的风险"""
    return random.choice(_USER_AGENTS)


async def _random_delay(min_sec: float = 2.0, max_sec: float = 5.0) -> None:
    """随机延迟，模拟人类行为，避免被识别为机器人"""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


# ------------------------------------------------------------------
# Playwright 浏览器池（模块级单例）
# ------------------------------------------------------------------


class _BrowserPool:
    """Playwright 浏览器实例池（模块级单例）

    复用单个浏览器实例，避免每次请求重新启动 Chromium。
    每次请求创建独立的 BrowserContext（隔离 Cookie/Storage）。
    """

    def __init__(self) -> None:
        self._browser: Any = None
        self._playwright: Any = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> None:
        """确保浏览器实例已启动，使用双检查锁定模式避免并发启动"""
        if self._browser is None:
            async with self._lock:
                if self._browser is None:  # double-check
                    try:
                        from playwright.async_api import async_playwright
                    except ImportError:
                        raise ImportError(
                            "Playwright 未安装。安装方式: "
                            "pip install playwright && python -m playwright install chromium"
                        )
                    self._playwright = await async_playwright().start()
                    # 启动 headless 模式的 Chromium 浏览器
                    self._browser = await self._playwright.chromium.launch(headless=True)

    async def get_page(self) -> Any:
        """创建新的 BrowserContext + Page（隔离 Cookie/Storage）
        
        每次请求都创建独立的 BrowserContext，确保会话隔离。
        """
        await self._ensure_browser()
        # 创建新的上下文，使用随机 User-Agent
        context = await self._browser.new_context(user_agent=_random_ua())
        page = await context.new_page()
        return page

    async def shutdown(self) -> None:
        """关闭浏览器和 Playwright 实例（幂等）
        
        线程安全关闭，避免多次调用导致异常。
        """
        async with self._lock:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("browser close error: %s", exc)
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as exc:  # noqa: BLE001
                    logger.debug("playwright stop error: %s", exc)
                self._playwright = None

    async def close(self) -> None:
        """``shutdown`` 的历史别名"""
        await self.shutdown()


_browser_pool: _BrowserPool | None = None


def _get_browser_pool() -> _BrowserPool:
    """获取模块级浏览器池单例
    
    首次调用时创建实例，后续调用返回同一实例。
    """
    global _browser_pool
    if _browser_pool is None:
        _browser_pool = _BrowserPool()
    return _browser_pool


def _atexit_shutdown_browser_pool() -> None:
    """进程退出时关闭浏览器池，避免僵尸 Chromium 进程
    
    在 Python 进程退出时注册此函数，确保浏览器被正确关闭。
    """
    pool = _browser_pool
    if pool is None or pool._browser is None:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，创建新循环来关闭浏览器
        try:
            asyncio.run(pool.shutdown())
        except Exception as exc:  # noqa: BLE001
            logger.debug("atexit browser pool shutdown failed: %s", exc)


atexit.register(_atexit_shutdown_browser_pool)


class GooglePatentsClient:
    """Google Patents 爬虫客户端 (兜底方案)

    ⚠️ 无官方 API，通过网页抓取获取数据。
    建议优先使用 PatentsView、EPO OPS 等官方数据源。

    抓取策略:
    1. httpx + BeautifulSoup 静态解析（优先）
    2. Playwright 动态渲染（可选，需安装 ``playwright``）

    Attributes:
        BASE_URL: Google Patents 网站地址
    """

    BASE_URL = "https://patents.google.com"

    def __init__(self, use_playwright: bool = False) -> None:
        """初始化 Google Patents 爬虫客户端

        Args:
            use_playwright: 是否启用 Playwright 动态渲染兜底。
                            需要额外安装: ``pip install playwright``
        """
        self._http = SouWenHttpClient(
            base_url=self.BASE_URL,
            headers={"User-Agent": _random_ua()},
            source_name="google_patents",
        )
        self._use_playwright = use_playwright
        # 保守限流：约 10 req/min（Google Patents 反爬比较严格）
        self._limiter = TokenBucketLimiter(rate=0.16, burst=2)

    async def __aenter__(self) -> GooglePatentsClient:
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._http.__aexit__(*args)

    async def close(self) -> None:
        """关闭 HTTP 连接"""
        await self._http.close()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        num_results: int = 10,
    ) -> SearchResponse:
        """搜索 Google Patents

        Args:
            query: 搜索关键词
            num_results: 期望返回结果数

        Returns:
            SearchResponse 封装的搜索结果
        """
        await self._limiter.acquire()
        await _random_delay()

        # 先尝试静态解析（快速）
        patents = await self._search_static(query, num_results)

        # 静态解析失败且启用 Playwright 时尝试动态渲染
        if not patents and self._use_playwright:
            logger.info("静态解析无结果，尝试 Playwright 动态渲染")
            patents = await self._search_playwright(query, num_results)

        return SearchResponse(
            query=query,
            source=SourceType.GOOGLE_PATENTS,
            total_results=len(patents),
            results=patents,
            page=1,
            per_page=num_results,
        )

    async def get_patent(self, patent_id: str) -> PatentResult:
        """获取专利详情

        Args:
            patent_id: 专利号，例如 ``"US11234567B2"``

        Returns:
            PatentResult 模型

        Raises:
            NotFoundError: 未找到该专利
        """
        await self._limiter.acquire()
        await _random_delay()

        result = await self._get_patent_static(patent_id)

        if result is None and self._use_playwright:
            logger.info("静态解析失败，尝试 Playwright 动态渲染")
            result = await self._get_patent_playwright(patent_id)

        if result is None:
            raise NotFoundError(f"专利 {patent_id} 未找到或无法解析")
        return result

    # ------------------------------------------------------------------
    # 策略 1: httpx + BeautifulSoup 静态解析
    # ------------------------------------------------------------------

    async def _search_static(
        self,
        query: str,
        num_results: int,
    ) -> list[PatentResult]:
        """使用 httpx + BeautifulSoup 抓取搜索结果
        
        若 BeautifulSoup 未安装或请求失败，返回空列表。
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4 未安装，跳过静态解析")
            return []

        # 每次请求更换 UA，模拟不同用户
        headers = {"User-Agent": _random_ua()}
        resp = await self._http.get(
            "/",
            params={"q": query, "num": num_results, "oq": query},
            headers=headers,
        )

        if resp.status_code != 200:
            logger.warning("Google Patents 搜索返回 %d", resp.status_code)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_search_page(soup)

    async def _get_patent_static(
        self,
        patent_id: str,
    ) -> PatentResult | None:
        """使用 httpx + BeautifulSoup 抓取专利详情
        
        若无法解析返回 None，调用者可选择使用 Playwright 兜底。
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4 未安装，跳过静态解析")
            return None

        headers = {"User-Agent": _random_ua()}
        resp = await self._http.get(
            f"/patent/{patent_id}",
            headers=headers,
        )

        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning("Google Patents 详情返回 %d", resp.status_code)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_detail_page(soup, patent_id)

    @staticmethod
    def _parse_search_page(soup: Any) -> list[PatentResult]:
        """解析搜索结果页面
        
        支持多种 Google Patents 页面结构和 CSS 选择器。
        """
        results: list[PatentResult] = []

        # Google Patents 搜索结果在 <search-result-item> 或 article 标签中
        items = soup.select("search-result-item, article.result")
        if not items:
            # 备用选择器
            items = soup.select("[data-result]")

        for item in items:
            try:
                # 标题：尝试多个可能的选择器
                title_elem = item.select_one("h3, .result-title, [id*='title']")
                title = title_elem.get_text(strip=True) if title_elem else ""

                # 专利号
                id_elem = item.select_one(".result-id, [data-patent-id], span.patent-number")
                patent_id = id_elem.get_text(strip=True) if id_elem else ""

                # 摘要
                abs_elem = item.select_one(".result-snippet, .abstract, [id*='abstract']")
                abstract = abs_elem.get_text(strip=True) if abs_elem else None

                # 申请人 / 受让人
                assignee_elem = item.select_one(".result-assignee, [id*='assignee']")
                applicants: list[Applicant] = []
                if assignee_elem:
                    applicants.append(Applicant(name=assignee_elem.get_text(strip=True)))

                # 至少有标题或专利号才构造结果
                if title or patent_id:
                    results.append(
                        PatentResult(
                            source=SourceType.GOOGLE_PATENTS,
                            title=title,
                            patent_id=patent_id,
                            applicants=applicants,
                            abstract=abstract,
                            source_url=f"https://patents.google.com/patent/{patent_id}"
                            if patent_id
                            else "",
                        )
                    )
            except Exception:
                logger.debug("跳过无法解析的搜索结果项", exc_info=True)

        return results

    @staticmethod
    def _parse_detail_page(
        soup: Any,
        patent_id: str,
    ) -> PatentResult | None:
        """解析专利详情页面
        
        提取标题、摘要、发明人、申请人、分类号、日期等信息。
        """
        try:
            # 标题
            title_elem = soup.select_one("h1#title, [data-invention-title], .patent-title")
            title = title_elem.get_text(strip=True) if title_elem else ""

            # 摘要
            abs_elem = soup.select_one("section#abstract .abstract, div.abstract")
            abstract = abs_elem.get_text(strip=True) if abs_elem else None

            # 发明人：使用 schema.org microdata 或 data 属性
            inventors: list[str] = []
            for inv in soup.select("[itemprop='inventor'] [itemprop='name']"):
                name = inv.get_text(strip=True)
                if name:
                    inventors.append(name)

            # 受让人 / 申请人
            applicants: list[Applicant] = []
            for assignee in soup.select(
                "[itemprop='assigneeCurrent'] [itemprop='name'],[data-assignee]"
            ):
                name = assignee.get_text(strip=True)
                if name:
                    applicants.append(Applicant(name=name))

            # CPC 分类号
            cpc_codes: list[str] = []
            for c in soup.select("[itemprop='cpcs'] [itemprop='Code']"):
                code = c.get_text(strip=True)
                if code:
                    cpc_codes.append(code)

            # 公开日期（可能存储在 content 属性或文本中）
            pub_date = None
            date_elem = soup.select_one("[itemprop='publicationDate']")
            if date_elem:
                pub_date = safe_parse_date(date_elem.get("content", date_elem.get_text(strip=True)))

            # 权利要求
            claims: str | None = None
            claims_elem = soup.select_one("section#claims")
            if claims_elem:
                claims = claims_elem.get_text(strip=True)

            return PatentResult(
                source=SourceType.GOOGLE_PATENTS,
                title=title,
                patent_id=patent_id,
                publication_date=pub_date,
                applicants=applicants,
                inventors=inventors,
                abstract=abstract,
                claims=claims,
                cpc_codes=cpc_codes,
                source_url=f"https://patents.google.com/patent/{patent_id}",
            )
        except Exception as exc:
            logger.warning("Google Patents 详情页解析失败: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 策略 2: Playwright 动态渲染 (可选)
    # ------------------------------------------------------------------

    async def _search_playwright(
        self,
        query: str,
        num_results: int,
    ) -> list[PatentResult]:
        """使用 Playwright 动态渲染搜索结果（复用浏览器池）
        
        此为兜底方案，当静态解析失败时使用。
        """
        pool = _get_browser_pool()
        try:
            page = await pool.get_page()
        except ImportError:
            logger.warning(
                "Playwright 未安装。安装方式: pip install playwright && python -m playwright install chromium"
            )
            return []

        results: list[PatentResult] = []
        try:
            url = f"{self.BASE_URL}/?q={query}&num={num_results}"
            # 等待网络空闲（所有请求完成）后再解析
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            results = self._parse_search_page(soup)
        except Exception as exc:
            logger.warning("Playwright 搜索失败: %s", exc)
        finally:
            # 关闭上下文（页面会自动关闭）
            await page.context.close()

        return results

    async def _get_patent_playwright(
        self,
        patent_id: str,
    ) -> PatentResult | None:
        """使用 Playwright 动态渲染专利详情（复用浏览器池）
        
        此为兜底方案，当静态解析失败时使用。
        """
        pool = _get_browser_pool()
        try:
            page = await pool.get_page()
        except ImportError:
            logger.warning(
                "Playwright 未安装。安装方式: pip install playwright && python -m playwright install chromium"
            )
            return None

        result: PatentResult | None = None
        try:
            url = f"{self.BASE_URL}/patent/{patent_id}"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(content, "html.parser")
            result = self._parse_detail_page(soup, patent_id)
        except Exception as exc:
            logger.warning("Playwright 获取详情失败: %s", exc)
        finally:
            await page.context.close()

        return result


def _safe_date(value: str | None):
    """``safe_parse_date`` 的向后兼容别名
    
    供旧代码调用，新代码应直接使用 safe_parse_date。
    """
    return safe_parse_date(value)

