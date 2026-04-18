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
    - souwen.scraper.base.BaseScraper: 爬虫基类（提供 TLS 指纹、限流、重试）
    - souwen.models: 统一数据模型
    - souwen.exceptions: NotFoundError
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from souwen.models import PatentResult, Applicant, SearchResponse, SourceType
from souwen.exceptions import NotFoundError
from souwen.scraper.base import BaseScraper

logger = logging.getLogger("souwen.scraper.google_patents")

GOOGLE_PATENTS_BASE = "https://patents.google.com"


class GooglePatentsScraper(BaseScraper):
    """Google Patents 爬虫实现 — 兜底方案

    ⚠️ 重要声明：
    Google Patents 无官方 API。此模块通过爬虫方式获取数据。
    建议优先使用官方 API：PatentsView、EPO OPS、PQAI 等。

    策略优先级：
    1. XHR 接口 (xhr/query) - 优先，返回 JSON 格式
    2. HTML 页面解析 - 回退方案，使用 BeautifulSoup 静态解析
    3. Playwright 动态渲染 - 可选（需安装可选依赖，本文件未实现）

    Args:
        min_delay: 请求最小间隔（秒），默认 3.0（较长的延迟以礼貌对待 Google）
        max_delay: 请求最大间隔（秒），默认 6.0
    """

    ENGINE_NAME = "google_patents"

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
        url = f"{GOOGLE_PATENTS_BASE}/xhr/query"
        params = {
            "url": f"q={quote_plus(query)}&num={num_results}",
            "exp": "",
        }

        try:
            resp = await self._fetch(url, params=params)
        except Exception:
            # 静态方式失败，尝试从搜索页面解析
            logger.info("XHR 接口失败，尝试从 HTML 页面解析")
            return await self._search_html(query, num_results)

        if resp.status_code == 200:
            try:
                return self._parse_search_response(resp.json(), query)
            except Exception as e:
                logger.warning("XHR 响应解析失败: %s，回退 HTML 解析", e)
                return await self._search_html(query, num_results)

        return await self._search_html(query, num_results)

    async def _search_html(self, query: str, num_results: int) -> SearchResponse:
        """从 HTML 页面解析搜索结果 — 回退方案

        当 XHR 接口失败时调用此方法。使用 BeautifulSoup 解析静态 HTML。

        Args:
            query: 搜索关键词
            num_results: 最大返回结果数

        Returns:
            SearchResponse：可能为空结果集（若页面无法解析）
        """
        url = f"{GOOGLE_PATENTS_BASE}/"
        params = {"q": query, "num": str(num_results)}

        resp = await self._fetch(url, params=params)
        if resp.status_code != 200:
            return SearchResponse(
                query=query,
                source=SourceType.GOOGLE_PATENTS,
                total_results=0,
                results=[],
            )

        soup = BeautifulSoup(resp.text, "lxml")
        results: list[PatentResult] = []

        # 尝试解析搜索结果条目
        for item in soup.select("search-result-item, article, .result-item"):
            try:
                patent = self._parse_search_item(item)
                if patent:
                    results.append(patent)
            except Exception as e:
                logger.debug("解析搜索条目失败: %s", e)
                continue

        return SearchResponse(
            query=query,
            source=SourceType.GOOGLE_PATENTS,
            total_results=len(results),
            results=results,
        )

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
            source=SourceType.GOOGLE_PATENTS,
            total_results=len(results),
            results=results,
        )

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
        title_el = item.select_one("h3, .title, [data-title]")
        title = title_el.get_text(strip=True) if title_el else None
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
                source_url = f"{GOOGLE_PATENTS_BASE}/patent/{patent_id}"

        if not patent_id:
            return None

        # 提取摘要
        abstract_el = item.select_one(".abstract, [data-abstract], p")
        abstract = abstract_el.get_text(strip=True) if abstract_el else None

        return PatentResult(
            source=SourceType.GOOGLE_PATENTS,
            title=title,
            patent_id=patent_id,
            abstract=abstract,
            source_url=source_url or f"{GOOGLE_PATENTS_BASE}",
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
        publication_number = data.get("publication_number", "")
        title = data.get("title", "未知标题")

        # 解析申请人
        applicants = []
        for assignee in data.get("assignee", []):
            if isinstance(assignee, str):
                applicants.append(Applicant(name=assignee))
            elif isinstance(assignee, dict):
                applicants.append(Applicant(name=assignee.get("name", "")))

        # 解析日期
        pub_date = None
        date_str = data.get("publication_date", "")
        if date_str and len(date_str) == 8:
            try:
                pub_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                pass

        return PatentResult(
            source=SourceType.GOOGLE_PATENTS,
            title=title if isinstance(title, str) else str(title),
            patent_id=publication_number,
            publication_date=pub_date,
            applicants=applicants,
            inventors=data.get("inventor", []),
            abstract=data.get("abstract", {}).get("text", None)
            if isinstance(data.get("abstract"), dict)
            else data.get("abstract"),
            ipc_codes=data.get("ipc", []),
            cpc_codes=data.get("cpc", []),
            source_url=f"{GOOGLE_PATENTS_BASE}/patent/{publication_number}",
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
        url = f"{GOOGLE_PATENTS_BASE}/patent/{patent_id}/en"

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
            source=SourceType.GOOGLE_PATENTS,
            title=title,
            patent_id=patent_id,
            inventors=inventors,
            applicants=applicants,
            abstract=abstract,
            claims=claims,
            ipc_codes=ipc_codes,
            cpc_codes=cpc_codes,
            source_url=f"{GOOGLE_PATENTS_BASE}/patent/{patent_id}/en",
            raw={},
        )
