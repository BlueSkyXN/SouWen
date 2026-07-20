"""Google Patents 爬虫实现

⚠️ 这是兜底方案，优先使用官方 API（PatentsView、EPO OPS 等）。
Google Patents 无官方 API，本模块通过爬虫方式获取数据。

策略优先级：
1. httpx + BeautifulSoup 静态解析（优先）
2. Playwright 动态渲染（回退方案，需安装可选依赖）

文件用途：
    继承 BaseScraper 的 Google Patents 专用爬虫，封装搜索与详情两类爬取流程。
    采用 XHR 接口优先、HTML 页面解析回退的双策略，最大化兼容 Google Patents 的页面变化。
    与 ``patent.google_patents.GooglePatentsClient`` 不同：
    本模块复用 BaseScraper 的 TLS 指纹和自适应退避能力，定位为 ``scraper`` 子系统的实现。

函数/类清单：
    GooglePatentsScraper（类，继承 BaseScraper）
        - 功能：Google Patents 专用爬虫，提供搜索和详情爬取
        - 类属性：ENGINE_NAME 频道标识符（用于配置解析）

    search(query, num_results=10) -> SearchResponse
        - 功能：搜索 Google Patents（XHR 优先，HTML 回退）
        - 输入：query 搜索关键词，num_results 期望返回数量
        - 输出：统一 SearchResponse

    _search_html(query, num_results) -> SearchResponse
        - 功能：HTML 页面解析回退方案，使用 BeautifulSoup 提取搜索条目

    _parse_search_response(data, query) -> SearchResponse
        - 功能：解析 XHR JSON 响应（防御性解析，逐层校验数据结构）

    _parse_search_item(item) -> PatentResult | None
        - 功能：从单个 HTML 元素中提取专利标题、专利号、摘要

    _map_patent(data: dict) -> PatentResult
        - 功能：将 XHR 返回的专利数据字典映射为 PatentResult 对象
        - 注意：日期字段为 YYYYMMDD 格式，需要拆分转换

    get_patent(patent_id: str) -> PatentResult
        - 功能：爬取专利详情页 ``/patent/<id>/en``，提取标题/摘要/权利要求/分类号等字段
        - 异常：NotFoundError 页面 404 时抛出

模块依赖：
    - bs4 (BeautifulSoup): HTML 解析
    - souwen.core.scraper.base.BaseScraper: 爬虫基类（提供 TLS 指纹、限流、重试）
    - souwen.models: 统一数据模型
    - souwen.core.exceptions: NotFoundError
"""

from __future__ import annotations

import inspect
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import quote_plus, urlencode

from bs4 import BeautifulSoup

from souwen.config import get_config
from souwen.core.browser_pool import get_browser_pool
from souwen.core.exceptions import ConfigError, NotFoundError, SourceUnavailableError
from souwen.core.scraper.base import BaseScraper
from souwen.models import Applicant, PatentResult, SearchResponse

logger = logging.getLogger("souwen.patent.google_patents_scraper")

GOOGLE_PATENTS_BASE = "https://patents.google.com"
_SEARCH_RESULT_SELECTOR = "search-result-item, article, .result-item"
_PLAYWRIGHT_HEADER_EXCLUDE = frozenset({"user-agent", "accept-encoding", "connection"})
_GOOGLE_BLOCK_TEXT_MARKERS = (
    "but your computer or network may be sending automated queries",
    "to protect our users, we can't process your request right now",
)


class GooglePatentsScraper(BaseScraper):
    """Google Patents 爬虫实现 — 兜底方案

    ⚠️ 重要声明：
    Google Patents 无官方 API。此模块通过爬虫方式获取数据。
    建议优先使用官方 API：PatentsView、EPO OPS、PQAI 等。

    策略优先级：
    1. XHR 接口 (xhr/query) - 优先，返回 JSON 格式
    2. HTML 页面解析 - 回退方案，使用 BeautifulSoup 静态解析
    3. Playwright 动态渲染 - 可选 fallback（需安装可选依赖和浏览器 runtime）

    Args:
        min_delay: 请求最小间隔（秒），默认 3.0（较长的延迟以礼貌对待 Google）
        max_delay: 请求最大间隔（秒），默认 6.0
    """

    ENGINE_NAME = "google_patents"
    BASE_URL = GOOGLE_PATENTS_BASE

    def __init__(self, min_delay: float = 3.0, max_delay: float = 6.0):
        super().__init__(min_delay=min_delay, max_delay=max_delay, max_retries=3)

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """搜索 Google Patents — 双策略降级

        流程：
        1. 优先尝试 XHR 接口 (patents.google.com/xhr/query)
        2. 若失败或解析错误，回退到 HTML 页面解析
        3. 返回统一的 SearchResponse

        Args:
            query: 搜索关键词
            num_results: 最大返回结果数

        Returns:
            SearchResponse：统一搜索响应格式
        """
        logger.info("[Google Patents] 搜索: %s (兜底爬虫)", query)
        url = f"{self._resolved_base_url}/xhr/query"
        params = {
            "url": f"q={quote_plus(query)}&num={num_results}",
            "exp": "",
        }

        try:
            resp = await self._fetch(url, params=params)
        except Exception as exc:
            logger.info("XHR 接口失败，尝试从 HTML 页面解析: %s", exc)
        else:
            if resp.status_code == 200:
                try:
                    parsed = self._parse_search_response(resp.json(), query)
                    if parsed.results:
                        return parsed
                    logger.info("XHR 接口返回空结果，尝试 HTML/Playwright fallback")
                except Exception as e:
                    logger.warning("XHR 响应解析失败: %s，回退 HTML 解析", e)

        return await self._search_html(query, num_results)

    @staticmethod
    def _empty_response(query: str) -> SearchResponse:
        return SearchResponse(
            query=query,
            source="google_patents",
            total_results=0,
            results=[],
        )

    async def _search_html(self, query: str, num_results: int) -> SearchResponse:
        """从 HTML 页面解析搜索结果 — 回退方案

        当 XHR 接口失败时调用此方法。使用 BeautifulSoup 解析静态 HTML。

        Args:
            query: 搜索关键词
            num_results: 最大返回结果数

        Returns:
            SearchResponse：可能为空结果集（若页面无法解析）
        """
        url = f"{self._resolved_base_url}/"
        params = {"q": query, "num": str(num_results)}

        static_response = self._empty_response(query)
        static_failed = False
        try:
            resp = await self._fetch(url, params=params)
        except Exception as exc:
            static_failed = True
            logger.info("HTML 静态解析请求失败，尝试 Playwright fallback: %s", exc)
        else:
            if resp.status_code == 200:
                static_response = self._parse_search_html(resp.text, query)
                if static_response.results:
                    return static_response

        browser_response = await self._search_html_with_browser(query, num_results)
        if browser_response is not None:
            return browser_response
        if static_failed:
            raise SourceUnavailableError(
                "Google Patents search unavailable after XHR and HTML fallback failures"
            )
        return static_response

    def _parse_search_html(self, html: str, query: str) -> SearchResponse:
        """Parse Google Patents search HTML into normalized patent results."""

        soup = BeautifulSoup(html, "lxml")
        results: list[PatentResult] = []

        # 尝试解析搜索结果条目
        for item in soup.select(_SEARCH_RESULT_SELECTOR):
            try:
                patent = self._parse_search_item(item)
                if patent:
                    results.append(patent)
            except Exception as e:
                logger.debug("解析搜索条目失败: %s", e)
                continue

        return SearchResponse(
            query=query,
            source="google_patents",
            total_results=len(results),
            results=results,
        )

    def _browser_headers(self) -> dict[str, str]:
        """Return browser context headers that Playwright can safely override."""

        headers = {
            key: value
            for key, value in self._fingerprint.headers.items()
            if key.lower() not in _PLAYWRIGHT_HEADER_EXCLUDE
        }
        if self._channel_headers:
            headers.update(self._channel_headers)
        return headers

    async def _search_html_with_browser(
        self,
        query: str,
        num_results: int,
    ) -> SearchResponse | None:
        """Render the search page with the shared Playwright pool when available."""

        params = urlencode({"q": query, "num": str(num_results)})
        url = f"{self._resolved_base_url}/?{params}"
        timeout_ms = max(5000, int(get_config().timeout * 1000))

        try:
            pool = get_browser_pool(source_name=self.ENGINE_NAME)
            async with pool.page(
                user_agent=self._fingerprint.user_agent,
                extra_http_headers=self._browser_headers(),
            ) as page:
                await self._install_page_ssrf_guard(page)
                page_response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                await self._wait_for_search_results(page, timeout_ms=min(timeout_ms, 5000))
                html = await page.content()
                status_code = getattr(page_response, "status", None)
        except ConfigError as exc:
            logger.info("Playwright 未安装，跳过 Google Patents 动态渲染 fallback: %s", exc)
            return None
        except SourceUnavailableError:
            raise
        except Exception as exc:
            logger.warning("Google Patents Playwright fallback 失败: %s", exc)
            return None

        block_message = self._google_block_message(status_code, html)
        if block_message:
            raise SourceUnavailableError(block_message)

        response = self._parse_search_html(html, query)
        if response.results:
            logger.info("Google Patents Playwright fallback 返回 %d 条结果", len(response.results))
        return response

    @staticmethod
    def _google_block_message(status_code: Any, html: str) -> str | None:
        """Return a diagnostic message for Google's anti-automation block page."""

        text = GooglePatentsScraper._clean_text(html).lower()
        has_block_text = any(marker in text for marker in _GOOGLE_BLOCK_TEXT_MARKERS)
        if status_code in {429, 503} and has_block_text:
            return (
                f"Google Patents blocked automated search requests (HTTP {status_code} Sorry page)"
            )
        if has_block_text:
            return "Google Patents blocked automated search requests (Sorry page)"
        return None

    async def _wait_for_search_results(self, page: Any, *, timeout_ms: int) -> None:
        """Wait briefly for result nodes, but keep empty pages non-fatal."""

        wait_for_selector = getattr(page, "wait_for_selector", None)
        if wait_for_selector is None:
            return
        try:
            result = wait_for_selector(_SEARCH_RESULT_SELECTOR, timeout=timeout_ms)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.debug("Google Patents Playwright fallback 未等到搜索结果节点")

    @staticmethod
    async def _call_route_method(route: Any, method_name: str) -> None:
        method = getattr(route, method_name, None)
        if method is None:
            return
        result = method()
        if inspect.isawaitable(result):
            await result

    async def _install_page_ssrf_guard(self, page: Any) -> None:
        """Install request interception so dynamic rendering cannot fetch private URLs."""

        from souwen.web.fetch import validate_fetch_url

        async def _guard_route(route: Any) -> None:
            request = getattr(route, "request", None)
            target_url = str(getattr(request, "url", "") or "")
            ok, reason = validate_fetch_url(target_url)
            if ok:
                proceed = "fallback" if hasattr(route, "fallback") else "continue_"
                await self._call_route_method(route, proceed)
                return

            logger.warning(
                "Google Patents browser SSRF blocked: url=%s reason=%s",
                target_url,
                reason,
            )
            await self._call_route_method(route, "abort")

        route = getattr(page, "route", None)
        if route is None:
            return
        result = route("**/*", _guard_route)
        if inspect.isawaitable(result):
            await result

    def _parse_search_response(self, data: Any, query: str) -> SearchResponse:
        """解析 XHR 搜索响应 — 防御性解析

        Google Patents XHR 响应格式可能变化，本方法采用防御性策略：
        - 逐层检查数据结构是否存在
        - 异常时捕获和记录，继续处理下一条

        Args:
            data: XHR 响应的 JSON 数据
            query: 原始搜索关键词

        Returns:
            SearchResponse：可能为空结果集
        """
        results: list[PatentResult] = []

        # Google Patents XHR 响应格式可能变化，做防御性解析
        if isinstance(data, dict):
            clusters = data.get("results", {}).get("cluster", [])
            for cluster in clusters:
                for result in cluster.get("result", []):
                    patent_data = result.get("patent", {})
                    if patent_data:
                        try:
                            patent = self._map_patent(patent_data)
                            results.append(patent)
                        except Exception as e:
                            logger.debug("解析专利数据失败: %s", e)

        return SearchResponse(
            query=query,
            source="google_patents",
            total_results=len(results),
            results=results,
        )

    @staticmethod
    def _clean_text(value: Any) -> str:
        """Normalize Google Patents text fields that may contain HTML fragments."""

        if value is None:
            return ""
        text = BeautifulSoup(str(value), "lxml").get_text(" ", strip=True)
        return " ".join(text.split())

    @classmethod
    def _as_text_list(cls, value: Any) -> list[str]:
        """Normalize upstream scalar/list/dict people and classification fields."""

        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            values = [value]

        result: list[str] = []
        for item in values:
            if isinstance(item, dict):
                item = item.get("name") or item.get("text") or item.get("value") or ""
            text = cls._clean_text(item)
            if text:
                result.append(text)
        return result

    @classmethod
    def _abstract_text(cls, data: dict[str, Any]) -> str | None:
        abstract = data.get("abstract")
        if isinstance(abstract, dict):
            abstract = abstract.get("text") or abstract.get("html") or ""
        text = cls._clean_text(abstract)
        if not text:
            text = cls._clean_text(data.get("snippet"))
        return text or None

    @classmethod
    def _google_date(cls, value: Any) -> date | None:
        text = cls._clean_text(value)
        if not text:
            return None
        if len(text) == 8 and text.isdigit():
            text = f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    def _parse_search_item(self, item: Any) -> PatentResult | None:
        """从 HTML 元素解析单个搜索结果

        使用多种选择器适配页面变化（h3、.title、[data-title] 等）。
        核心字段：标题、专利号、摘要。

        Args:
            item: BeautifulSoup HTML 元素

        Returns:
            PatentResult 或 None（若关键字段缺失）
        """
        # 尝试多种选择器，适配页面变化
        title_el = item.select_one("h3, .title, [data-title], a[href*='/patent/']")
        title = None
        if title_el:
            title = (
                title_el.get("data-title") or title_el.get("title") or title_el.get_text(strip=True)
            )
        if not title:
            return None

        # 提取专利号
        link_el = item.select_one("a[href*='/patent/']")
        patent_id = ""
        source_url = ""
        if link_el:
            href = link_el.get("href", "")
            match = re.search(r"/patent/([^/]+)", href)
            if match:
                patent_id = match.group(1)
                source_url = f"{self._resolved_base_url}/patent/{patent_id}"

        if not patent_id:
            return None

        # 提取摘要
        abstract_el = item.select_one(".abstract, [data-abstract], p")
        abstract = abstract_el.get_text(strip=True) if abstract_el else None

        return PatentResult(
            source="google_patents",
            title=title,
            patent_id=patent_id,
            abstract=abstract,
            source_url=source_url or f"{self._resolved_base_url}",
            raw={},
        )

    def _map_patent(self, data: dict) -> PatentResult:
        """从 XHR 数据映射为 PatentResult — 字段提取和类型转换

        提取以下字段：
        - 基础：publication_number、title
        - 人物：inventor、applicant/assignee
        - 分类：ipc、cpc
        - 内容：abstract（可能嵌套在字典中）
        - 时间：publication_date（YYYYMMDD 格式转 date 对象）

        Args:
            data: 来自 XHR 响应的专利数据字典

        Returns:
            PatentResult：完整的专利记录对象
        """
        publication_number = self._clean_text(data.get("publication_number", ""))
        title = self._clean_text(data.get("title")) or "未知标题"

        applicants = [Applicant(name=name) for name in self._as_text_list(data.get("assignee"))]
        inventors = self._as_text_list(data.get("inventor"))
        ipc_codes = self._as_text_list(data.get("ipc"))
        cpc_codes = self._as_text_list(data.get("cpc"))

        return PatentResult(
            source="google_patents",
            title=title,
            patent_id=publication_number,
            publication_date=self._google_date(data.get("publication_date")),
            filing_date=self._google_date(data.get("filing_date")),
            applicants=applicants,
            inventors=inventors,
            abstract=self._abstract_text(data),
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            source_url=f"{self._resolved_base_url}/patent/{publication_number}",
            raw=data,
        )

    async def get_patent(self, patent_id: str) -> PatentResult:
        """获取单个专利详情 — 深度爬取

        爬取专利详情页面 (patents.google.com/patent/{patent_id}/en)，
        提取标题、摘要、权利要求、发明人、申请人、分类号等详细信息。

        Args:
            patent_id: 专利公开号（如 US10123456B2）

        Returns:
            PatentResult：完整的专利详情

        Raises:
            NotFoundError：404 未找到专利
            ParseError：页面解析失败（隐式，返回部分数据）
        """
        logger.info("[Google Patents] 获取专利详情: %s (兜底爬虫)", patent_id)
        url = f"{self._resolved_base_url}/patent/{patent_id}/en"

        resp = await self._fetch(url)
        if resp.status_code == 404:
            raise NotFoundError(f"未找到专利: {patent_id}")

        soup = BeautifulSoup(resp.text, "lxml")

        # 提取标题
        title_el = soup.select_one("h1#title, .title, meta[name='DC.title']")
        title = ""
        if title_el:
            title = title_el.get("content", "") or title_el.get_text(strip=True)
        if not title:
            title = patent_id

        # 提取摘要
        abstract_el = soup.select_one("section.abstract div.abstract, .abstract")
        abstract = abstract_el.get_text(strip=True) if abstract_el else None

        # 提取权利要求
        claims_el = soup.select_one("section.claims, .claims")
        claims = claims_el.get_text(strip=True)[:5000] if claims_el else None

        # 提取发明人
        inventors = []
        for inv_el in soup.select("dd[itemprop='inventor'], .inventor"):
            name = inv_el.get_text(strip=True)
            if name:
                inventors.append(name)

        # 提取申请人
        applicants = []
        for app_el in soup.select("dd[itemprop='assigneeOriginal'], .assignee"):
            name = app_el.get_text(strip=True)
            if name:
                applicants.append(Applicant(name=name))

        # 提取 IPC/CPC 分类号
        ipc_codes = [
            el.get_text(strip=True) for el in soup.select(".IPC .code, [itemprop='ipcCode']")
        ]
        cpc_codes = [
            el.get_text(strip=True) for el in soup.select(".CPC .code, [itemprop='cpcCode']")
        ]

        return PatentResult(
            source="google_patents",
            title=title,
            patent_id=patent_id,
            inventors=inventors,
            applicants=applicants,
            abstract=abstract,
            claims=claims,
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            source_url=f"{self._resolved_base_url}/patent/{patent_id}/en",
            raw={},
        )
