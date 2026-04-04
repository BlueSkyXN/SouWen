"""Semantic Scholar Academic Graph API 客户端

官方文档: https://api.semanticscholar.org/api-docs/graph
鉴权: 可选 API Key (x-api-key)，无 Key 限流 100 req / 5 min
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.config import get_config
from souwen.exceptions import NotFoundError, ParseError, RateLimitError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import SlidingWindowLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.semanticscholar.org/graph/v1"

# 无 Key 限流: 100 次 / 300 秒
_DEFAULT_WINDOW_SIZE = 300
_DEFAULT_MAX_REQUESTS = 100

# 有 Key 限流较宽松
_KEYED_WINDOW_SIZE = 60
_KEYED_MAX_REQUESTS = 100

# 默认请求字段集
_DEFAULT_FIELDS = (
    "paperId,externalIds,title,abstract,year,authors,"
    "citationCount,referenceCount,isOpenAccess,openAccessPdf,"
    "publicationDate,venue,tldr"
)


class SemanticScholarClient:
    """Semantic Scholar 论文搜索客户端。

    Attributes:
        api_key: 可选 API Key，用于提升限流阈值。
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化客户端。

        Args:
            api_key: Semantic Scholar API Key。未提供时从全局配置读取。
        """
        cfg = get_config()
        self.api_key: str | None = api_key or getattr(
            cfg, "semantic_scholar_api_key", None
        )

        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        self._client = SouWenHttpClient(base_url=_BASE_URL, headers=headers)

        # 根据是否有 Key 选择限流策略
        if self.api_key:
            self._limiter = SlidingWindowLimiter(
                max_requests=_KEYED_MAX_REQUESTS,
                window_seconds=_KEYED_WINDOW_SIZE,
            )
        else:
            self._limiter = SlidingWindowLimiter(
                max_requests=_DEFAULT_MAX_REQUESTS,
                window_seconds=_DEFAULT_WINDOW_SIZE,
            )

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> SemanticScholarClient:
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

    def _parse_paper(self, data: dict[str, Any]) -> PaperResult:
        """将 S2 paper 对象转换为 PaperResult。

        Args:
            data: Semantic Scholar API 返回的 paper JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            authors = [
                Author(name=a.get("name", ""))
                for a in data.get("authors", [])
            ]

            external_ids: dict[str, str] = data.get("externalIds", {}) or {}
            doi = external_ids.get("DOI")
            arxiv_id = external_ids.get("ArXiv")

            # OA PDF
            oa_pdf: dict[str, str] | None = data.get("openAccessPdf")
            pdf_url: str | None = oa_pdf.get("url") if oa_pdf else None

            # tldr
            tldr_obj: dict[str, str] | None = data.get("tldr")
            tldr_text: str | None = tldr_obj.get("text") if tldr_obj else None

            return PaperResult(
                title=data.get("title", ""),
                authors=authors,
                abstract=data.get("abstract", ""),
                doi=doi,
                year=data.get("year"),
                publication_date=data.get("publicationDate"),
                source=SourceType.SEMANTIC_SCHOLAR,
                source_id=data.get("paperId", ""),
                url=f"https://www.semanticscholar.org/paper/{data.get('paperId', '')}",
                pdf_url=pdf_url,
                citation_count=data.get("citationCount"),
                extra={
                    "venue": data.get("venue"),
                    "tldr": tldr_text,
                    "arxiv_id": arxiv_id,
                    "reference_count": data.get("referenceCount"),
                    "is_open_access": data.get("isOpenAccess"),
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Semantic Scholar paper 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        fields: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> SearchResponse:
        """关键词搜索论文。

        Args:
            query: 检索关键词。
            fields: 逗号分隔的字段列表。默认使用完整字段集。
            limit: 返回条数，上限 100。
            offset: 偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。

        Raises:
            RateLimitError: 超出请求频率限制。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "query": query,
            "fields": fields or _DEFAULT_FIELDS,
            "limit": min(limit, 100),
            "offset": offset,
        }

        resp = await self._client.get("/paper/search", params=params)

        if resp.status_code == 429:
            raise RateLimitError("Semantic Scholar 请求频率超限，请稍后重试")

        data: dict[str, Any] = resp.json()

        results = [self._parse_paper(p) for p in data.get("data", [])]

        return SearchResponse(
            query=query,
            total=data.get("total", len(results)),
            page=(offset // limit) + 1 if limit else 1,
            per_page=limit,
            results=results,
            source=SourceType.SEMANTIC_SCHOLAR,
        )

    async def get_paper(self, paper_id: str) -> PaperResult:
        """通过 Paper ID / DOI / arXiv ID 获取论文详情。

        Args:
            paper_id: Semantic Scholar Paper ID、DOI (``DOI:xxx``)、
                      arXiv ID (``ARXIV:xxx``) 等。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: 论文不存在。
        """
        await self._limiter.acquire()

        params = {"fields": _DEFAULT_FIELDS}
        resp = await self._client.get(f"/paper/{paper_id}", params=params)

        if resp.status_code == 404:
            raise NotFoundError(f"Semantic Scholar 未找到论文: {paper_id}")
        if resp.status_code == 429:
            raise RateLimitError("Semantic Scholar 请求频率超限")

        return self._parse_paper(resp.json())

    async def get_recommendations(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> list[PaperResult]:
        """获取基于单篇论文的推荐列表。

        Args:
            paper_id: Semantic Scholar Paper ID。
            limit: 返回条数。

        Returns:
            推荐论文列表。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "fields": _DEFAULT_FIELDS,
            "limit": min(limit, 100),
        }

        resp = await self._client.get(
            f"/recommendations/v1/papers/forpaper/{paper_id}",
            params=params,
        )

        if resp.status_code == 404:
            raise NotFoundError(f"Semantic Scholar 未找到论文: {paper_id}")

        data: dict[str, Any] = resp.json()
        return [self._parse_paper(p) for p in data.get("recommendedPapers", [])]
