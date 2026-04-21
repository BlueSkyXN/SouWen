"""Europe PMC REST API 客户端

官方文档: https://europepmc.org/RestfulWebService
鉴权: 无需 Key
限流: 建议 ~10 req/s
返回: JSON

文件用途：Europe PMC 欧洲生物医学文献数据库搜索客户端，覆盖 PubMed/PMC、
预印本、专利等多种来源，提供摘要文本和开放获取全文链接。

函数/类清单：
    EuropepmcClient（类）
        - 功能：Europe PMC REST API 客户端，支持关键词全文搜索
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端,
                   _limiter (TokenBucketLimiter) 限流器（10 req/s）

    _parse_result(item: dict) -> PaperResult
        - 功能：将 Europe PMC result JSON 对象转换为 PaperResult
        - 输入：item resultList.result 数组中的单条 JSON
        - 输出：统一的 PaperResult 模型，包含 PMID、PMCID、DOI、摘要等字段

    search(query: str, page_size: int, page: int) -> SearchResponse
        - 功能：关键词搜索 Europe PMC 文献
        - 输入：query 检索词（支持布尔运算和字段限定），
               page_size 每页条数（最大 1000），page 页码（从 1 开始）
        - 输出：SearchResponse 包含结果列表及分页信息

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# Europe PMC 无硬限流，建议 ~10 req/s
_RATE_LIMIT_RPS = 10.0


class EuropepmcClient:
    """Europe PMC 生物医学文献搜索客户端。

    覆盖 PubMed、PMC、预印本（bioRxiv/medRxiv 等）、专利等多类型文献，
    提供结构化摘要和开放获取全文链接。
    """

    def __init__(self) -> None:
        """初始化 Europe PMC 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="europepmc")
        self._limiter = TokenBucketLimiter(rate=_RATE_LIMIT_RPS, burst=_RATE_LIMIT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> EuropepmcClient:
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
        """将 Europe PMC result 对象转换为 PaperResult。

        Args:
            item: Europe PMC resultList.result 数组中的单条 JSON 对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            title = (item.get("title") or "").strip()
            doi = item.get("doi") or None
            abstract = (item.get("abstractText") or "").strip() or None

            # 作者字段为逗号分隔字符串 "Smith J, Jones A, ..."
            author_str = item.get("authorString") or ""
            authors: list[Author] = []
            for name in author_str.split(","):
                name = name.strip().rstrip(".")
                if name:
                    authors.append(Author(name=name))

            # 发表年份
            year: int | None = None
            pub_year = item.get("pubYear")
            if pub_year:
                try:
                    year = int(str(pub_year))
                except (ValueError, TypeError):
                    pass

            pub_date: str | None = None
            if year:
                pub_date = f"{year}-01-01"

            # 期刊名
            journal = item.get("journalTitle") or item.get("bookOrReportDetails", {}).get(
                "publisher"
            ) or None

            # 标识符
            pmid = item.get("pmid")
            pmcid = item.get("pmcid")

            # 构建 URL：优先 PMC → PubMed → Europe PMC
            if pmcid:
                source_url = f"https://europepmc.org/article/PMC/{pmcid}"
                pdf_url = f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf"
            elif pmid:
                source_url = f"https://europepmc.org/article/MED/{pmid}"
                pdf_url = None
            else:
                ext_id = item.get("id", "")
                source = item.get("source", "")
                source_url = f"https://europepmc.org/article/{source}/{ext_id}" if ext_id else ""
                pdf_url = None

            # 被引用次数
            citation_count: int | None = None
            try:
                citation_count = int(item.get("citedByCount", 0)) or None
            except (ValueError, TypeError):
                pass

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.EUROPEPMC,
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=citation_count,
                journal=journal,
                raw={
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "source": item.get("source"),
                    "isOpenAccess": item.get("isOpenAccess"),
                    "inPMC": item.get("inPMC"),
                    "inEPMC": item.get("inEPMC"),
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Europe PMC 结果失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        page_size: int = 10,
        page: int = 1,
    ) -> SearchResponse:
        """关键词搜索 Europe PMC 文献。

        Args:
            query: 检索词，支持布尔运算（AND/OR/NOT）和字段限定（如 ``TITLE:cancer``）。
            page_size: 每页条数，最大 1000。
            page: 页码，从 1 开始。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "query": query,
            "resultType": "lite",
            "format": "json",
            "pageSize": min(page_size, 1000),
            "page": page,
        }

        resp = await self._client.get("/search", params=params)
        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise ParseError(f"Europe PMC JSON 解析失败: {exc}") from exc

        hit_count: int = 0
        try:
            hit_count = int(data.get("hitCount", 0))
        except (ValueError, TypeError):
            pass

        result_list = data.get("resultList", {}).get("result", [])
        results: list[PaperResult] = []
        for item in result_list:
            try:
                results.append(self._parse_result(item))
            except ParseError as exc:
                logger.warning("跳过解析失败的 Europe PMC 条目: %s", exc)

        return SearchResponse(
            query=query,
            total_results=hit_count or len(results),
            page=page,
            per_page=page_size,
            results=results,
            source=SourceType.EUROPEPMC,
        )
