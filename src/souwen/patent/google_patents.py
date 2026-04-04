"""Google Patents 爬虫客户端 (兜底方案)

Google Patents 无官方 API，采用爬虫方式获取数据。
优先使用 httpx + BeautifulSoup 静态解析；
如遇 JS 渲染页面，可选用 Playwright 动态渲染。

⚠️ 本模块为兜底方案，建议优先使用官方 API 数据源。
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import date
from typing import Any

from souwen.exceptions import NotFoundError
from souwen.http_client import SouWenHttpClient
from souwen.models import Applicant, PatentResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

# 随机 User-Agent 池
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


def _random_ua() -> str:
    """返回随机 User-Agent"""
    return random.choice(_USER_AGENTS)


async def _random_delay(min_sec: float = 2.0, max_sec: float = 5.0) -> None:
    """随机延迟，模拟人类行为"""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


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
        """初始化

        Args:
            use_playwright: 是否启用 Playwright 动态渲染兜底。
                            需要额外安装: ``pip install playwright``
        """
        self._http = SouWenHttpClient(
            base_url=self.BASE_URL,
            headers={"User-Agent": _random_ua()},
        )
        self._use_playwright = use_playwright
        # 保守限流：约 10 req/min
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
        self, query: str, num_results: int,
    ) -> list[PatentResult]:
        """使用 httpx + BeautifulSoup 抓取搜索结果"""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("beautifulsoup4 未安装，跳过静态解析")
            return []

        # 每次请求更换 UA
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
        self, patent_id: str,
    ) -> PatentResult | None:
        """使用 httpx + BeautifulSoup 抓取专利详情"""
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
        """解析搜索结果页面"""
        results: list[PatentResult] = []

        # Google Patents 搜索结果在 <search-result-item> 或 article 标签中
        items = soup.select("search-result-item, article.result")
        if not items:
            # 备用选择器
            items = soup.select("[data-result]")

        for item in items:
            try:
                # 标题
                title_elem = item.select_one("h3, .result-title, [id*='title']")
                title = title_elem.get_text(strip=True) if title_elem else ""

                # 专利号
                id_elem = item.select_one(
                    ".result-id, [data-patent-id], span.patent-number"
                )
                patent_id = id_elem.get_text(strip=True) if id_elem else ""

                # 摘要
                abs_elem = item.select_one(
                    ".result-snippet, .abstract, [id*='abstract']"
                )
                abstract = abs_elem.get_text(strip=True) if abs_elem else None

                # 申请人
                assignee_elem = item.select_one(
                    ".result-assignee, [id*='assignee']"
                )
                applicants: list[Applicant] = []
                if assignee_elem:
                    applicants.append(
                        Applicant(name=assignee_elem.get_text(strip=True))
                    )

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
        soup: Any, patent_id: str,
    ) -> PatentResult | None:
        """解析专利详情页面"""
        try:
            # 标题
            title_elem = soup.select_one(
                "h1#title, [data-invention-title], .patent-title"
            )
            title = title_elem.get_text(strip=True) if title_elem else ""

            # 摘要
            abs_elem = soup.select_one(
                "section#abstract .abstract, div.abstract"
            )
            abstract = abs_elem.get_text(strip=True) if abs_elem else None

            # 发明人
            inventors: list[str] = []
            for inv in soup.select("[itemprop='inventor'] [itemprop='name']"):
                name = inv.get_text(strip=True)
                if name:
                    inventors.append(name)

            # 受让人 / 申请人
            applicants: list[Applicant] = []
            for assignee in soup.select(
                "[itemprop='assigneeCurrent'] [itemprop='name'],"
                "[data-assignee]"
            ):
                name = assignee.get_text(strip=True)
                if name:
                    applicants.append(Applicant(name=name))

            # 分类号
            cpc_codes: list[str] = []
            for c in soup.select("[itemprop='cpcs'] [itemprop='Code']"):
                code = c.get_text(strip=True)
                if code:
                    cpc_codes.append(code)

            # 日期
            pub_date: date | None = None
            date_elem = soup.select_one("[itemprop='publicationDate']")
            if date_elem:
                pub_date = _safe_date(
                    date_elem.get("content", date_elem.get_text(strip=True))
                )

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
        self, query: str, num_results: int,
    ) -> list[PatentResult]:
        """使用 Playwright 动态渲染搜索结果"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning(
                "Playwright 未安装。安装方式: pip install playwright && python -m playwright install chromium"
            )
            return []

        results: list[PatentResult] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page(
                    user_agent=_random_ua(),
                )
                url = f"{self.BASE_URL}/?q={query}&num={num_results}"
                await page.goto(url, wait_until="networkidle", timeout=30000)
                content = await page.content()

                from bs4 import BeautifulSoup

                soup = BeautifulSoup(content, "html.parser")
                results = self._parse_search_page(soup)
            except Exception as exc:
                logger.warning("Playwright 搜索失败: %s", exc)
            finally:
                await browser.close()

        return results

    async def _get_patent_playwright(
        self, patent_id: str,
    ) -> PatentResult | None:
        """使用 Playwright 动态渲染专利详情"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning(
                "Playwright 未安装。安装方式: pip install playwright && python -m playwright install chromium"
            )
            return None

        result: PatentResult | None = None
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page(
                    user_agent=_random_ua(),
                )
                url = f"{self.BASE_URL}/patent/{patent_id}"
                await page.goto(url, wait_until="networkidle", timeout=30000)
                content = await page.content()

                from bs4 import BeautifulSoup

                soup = BeautifulSoup(content, "html.parser")
                result = self._parse_detail_page(soup, patent_id)
            except Exception as exc:
                logger.warning("Playwright 获取详情失败: %s", exc)
            finally:
                await browser.close()

        return result


def _safe_date(value: str | None) -> date | None:
    """安全解析日期字符串"""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
