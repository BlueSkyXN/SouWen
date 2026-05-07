"""Europe PMC API 客户端

官方文档: https://europepmc.org/RestfulWebService
鉴权: 无需 Key
限流: 宽松，建议保守 ~5 req/s
返回: JSON（resultList.result[]）

文件用途：Europe PMC（European PubMed Central）生物医学/生命科学文献搜索客户端，
聚合 PubMed、PMC、AGRICOLA 等多源开放获取论文，并提供全文/PDF 链接、引用计数、
开放获取标识等丰富元数据，免 Key 即用。

参考来源：Europe PMC RESTful Web Service v8
         https://www.ebi.ac.uk/europepmc/webservices/rest/search

函数/类清单：
    EuropePmcClient（类）
        - 功能：Europe PMC 搜索客户端，解析 JSON 响应为统一数据模型
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（5 req/s，保守设置）

    _parse_result(item: dict) -> PaperResult
        - 功能：将 Europe PMC 单条 result 转换为 PaperResult
        - 输入：Europe PMC API 响应 resultList.result[] 中的单条记录
        - 输出：统一的 PaperResult 模型，raw 中含 PMID/PMCID、关键词、开放获取标识等

    search(query: str, page_size: int = 10) -> SearchResponse
        - 功能：使用 Europe PMC 全文检索查找论文
        - 输入：query 检索式（支持字段限定如 PUB_YEAR、HAS_FT、OPEN_ACCESS、SRC）,
               page_size 返回条数（API 上限 1000）
        - 输出：SearchResponse 包含结果列表及分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse
from souwen.core.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# 保守限流：5 req/s
_DEFAULT_RPS = 5.0

# Europe PMC 数据源类型，待补充至 registry adapter name后即可替换为 'europepmc'
# 'europepmc' 已在 models.py 中注册


class EuropePmcClient:
    """Europe PMC 生物医学开放获取文献搜索客户端。

    特点:
        - 聚合 PubMed/PMC/AGRICOLA 等多源，覆盖生命科学全领域
        - 提供 isOpenAccess、HAS_FT、fullTextUrlList 等开放获取信号
        - 返回 citedByCount，可用于影响力筛选
        - 无需 API Key，零配置即用
    """

    def __init__(self) -> None:
        """初始化 Europe PMC 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="europepmc")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> EuropePmcClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_result(item: dict[str, Any]) -> PaperResult:
        """将 Europe PMC 单条 result 转换为 PaperResult。

        Europe PMC search API 在 ``resultList.result[]`` 下返回每条记录，
        关键字段示例：
        {
            "id": "12345678",
            "source": "MED",                # MED=PubMed, PMC=PubMed Central, AGR=AGRICOLA
            "pmid": "12345678",
            "pmcid": "PMC1234567",
            "doi": "10.xxxx/yyyy",
            "title": "...",
            "authorList": {"author": [{"fullName": "Doe J"}, ...]},
            "abstractText": "...",
            "pubYear": "2024",
            "firstPublicationDate": "2024-01-15",
            "journalTitle": "...",
            "citedByCount": 42,
            "isOpenAccess": "Y",
            "fullTextUrlList": {"fullTextUrl": [
                {"documentStyle": "pdf", "url": "..."},
                {"documentStyle": "html", "url": "..."}
            ]},
            "keywordList": {"keyword": ["..."]}
        }

        Args:
            item: Europe PMC API 响应中的单条 result 对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            paper_id: str = str(item.get("id", "") or "")
            pmid: str = str(item.get("pmid", "") or "")
            pmcid: str = str(item.get("pmcid", "") or "")
            ext_source: str = str(item.get("source", "") or "")  # MED/PMC/AGR

            title: str = item.get("title", "") or ""
            abstract: str = item.get("abstractText", "") or ""
            doi: str | None = item.get("doi") or item.get("doiId") or None
            journal: str | None = item.get("journalTitle") or None

            # 作者解析：authorList.author[] -> [{fullName: "..."}]
            authors: list[Author] = []
            author_list = item.get("authorList") or {}
            for author_item in (
                author_list.get("author", []) if isinstance(author_list, dict) else []
            ):
                if isinstance(author_item, dict):
                    name = author_item.get("fullName") or author_item.get("collectiveName") or ""
                else:
                    name = str(author_item)
                if name:
                    authors.append(Author(name=name))

            # 发表年份与日期
            pub_year_raw = item.get("pubYear")
            year: int | None = None
            if pub_year_raw:
                try:
                    year = int(str(pub_year_raw)[:4])
                except (ValueError, TypeError):
                    year = None
            pub_date: str | None = (
                item.get("firstPublicationDate") or item.get("electronicPublicationDate") or None
            )

            # 引用数
            citation_count: int | None = None
            cc_raw = item.get("citedByCount")
            if cc_raw is not None:
                try:
                    citation_count = int(cc_raw)
                except (ValueError, TypeError):
                    citation_count = None

            # PDF / 全文 URL：在 fullTextUrlList.fullTextUrl[] 中过滤 documentStyle in (html, pdf)
            pdf_url: str | None = None
            html_url: str | None = None
            full_text_urls = item.get("fullTextUrlList") or {}
            ft_entries = (
                full_text_urls.get("fullTextUrl", []) if isinstance(full_text_urls, dict) else []
            )
            for ft in ft_entries:
                if not isinstance(ft, dict):
                    continue
                style = (ft.get("documentStyle") or "").lower()
                url = ft.get("url")
                if not url:
                    continue
                if style == "pdf" and not pdf_url:
                    pdf_url = url
                elif style == "html" and not html_url:
                    html_url = url

            # source_url：优先使用 PMC（有全文）→ PMID → Europe PMC 内部页
            if pmcid:
                source_url = f"https://europepmc.org/article/PMC/{pmcid}"
            elif pmid:
                source_url = f"https://europepmc.org/article/MED/{pmid}"
            elif paper_id and ext_source:
                source_url = f"https://europepmc.org/article/{ext_source}/{paper_id}"
            elif html_url:
                source_url = html_url
            else:
                source_url = "https://europepmc.org/"

            # 开放获取与关键词
            is_open_access = (item.get("isOpenAccess") or "").upper() == "Y"
            keyword_list = item.get("keywordList") or {}
            keywords = keyword_list.get("keyword", []) if isinstance(keyword_list, dict) else []

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source="europepmc",
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=citation_count,
                journal=journal,
                open_access_url=html_url if is_open_access else None,
                raw={
                    "id": paper_id,
                    "pmid": pmid or None,
                    "pmcid": pmcid or None,
                    "ext_source": ext_source or None,
                    "is_open_access": is_open_access,
                    "keywords": keywords[:20] if isinstance(keywords, list) else [],
                    "html_url": html_url,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Europe PMC result 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        page_size: int = 10,
    ) -> SearchResponse:
        """使用 Europe PMC 检索文献。

        支持字段限定语法（拼接到 query 中），常用示例：
            - 年份范围：``(PUB_YEAR:[2020 TO 2024])``
            - 仅含全文：``(HAS_FT:Y)``
            - 仅开放获取：``(OPEN_ACCESS:Y)``
            - 限定来源：``(SRC:MED)`` / ``(SRC:PMC)`` / ``(SRC:AGR)``

        Args:
            query: 检索式。
            page_size: 返回结果数量（API 上限 1000）。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "query": query,
            "pageSize": min(max(page_size, 1), 1000),
            "format": "json",
            "resultType": "core",
            "cursorMark": "*",
        }

        resp = await self._client.get("/search", params=params)
        data: dict[str, Any] = resp.json()

        result_list = data.get("resultList") or {}
        items = result_list.get("result", []) if isinstance(result_list, dict) else []

        results: list[PaperResult] = []
        for item in items:
            try:
                results.append(self._parse_result(item))
            except ParseError as exc:
                logger.debug("跳过解析失败的 Europe PMC 论文: %s", exc)

        # hitCount 为字段名，而非 totalHits
        total_results: int
        try:
            total_results = int(data.get("hitCount", len(results)))
        except (ValueError, TypeError):
            total_results = len(results)

        return SearchResponse(
            query=query,
            total_results=total_results,
            page=1,
            per_page=page_size,
            results=results,
            source="europepmc",
        )
