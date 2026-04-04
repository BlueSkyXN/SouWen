"""DBLP API 客户端

官方文档: https://dblp.org/faq/How+to+use+the+dblp+search+API.html
鉴权: 无需 Key
限流: 宽松，无明确硬限制
"""

from __future__ import annotations

import logging
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_SEARCH_BASE_URL = "https://dblp.org/search"

# 保守限流
_DEFAULT_RPS = 5.0


class DblpClient:
    """DBLP 计算机科学文献搜索客户端。

    DBLP 专注于计算机科学领域，覆盖所有主流会议和期刊。
    """

    def __init__(self) -> None:
        """初始化 DBLP 客户端。"""
        self._client = SouWenHttpClient(base_url=_SEARCH_BASE_URL)
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> DblpClient:
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
    def _parse_hit(hit: dict[str, Any]) -> PaperResult:
        """将 DBLP hit 对象转换为 PaperResult。

        Args:
            hit: DBLP API 返回的单条 hit JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            info: dict[str, Any] = hit.get("info", {})

            title: str = info.get("title", "")
            # DBLP 标题末尾可能带句点
            if title.endswith("."):
                title = title[:-1]

            # 作者可能是字符串或列表
            raw_authors = info.get("authors", {}).get("author", [])
            if isinstance(raw_authors, dict):
                raw_authors = [raw_authors]
            elif isinstance(raw_authors, str):
                raw_authors = [{"text": raw_authors}]

            authors: list[Author] = []
            for a in raw_authors:
                name = a.get("text", a) if isinstance(a, dict) else str(a)
                if name:
                    authors.append(Author(name=name))

            # 年份
            year_str = info.get("year", "")
            year: int | None = None
            if year_str:
                try:
                    year = int(year_str)
                except ValueError:
                    pass

            # DOI
            doi: str | None = info.get("doi")

            # URL
            url: str | None = info.get("url") or info.get("ee")

            dblp_venue: str | None = info.get("venue") or None

            return PaperResult(
                title=title,
                authors=authors,
                abstract="",  # DBLP 不提供摘要
                doi=doi,
                year=year,
                publication_date=None,
                source=SourceType.DBLP,
                source_url=url,
                pdf_url=None,  # DBLP 不直接提供 PDF
                citation_count=None,
                venue=dblp_venue,
                raw={
                    "venue": info.get("venue"),
                    "type": info.get("type"),
                    "pages": info.get("pages"),
                    "volume": info.get("volume"),
                    "number": info.get("number"),
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 DBLP hit 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        hits: int = 10,
        first: int = 0,
    ) -> SearchResponse:
        """搜索 DBLP 文献。

        Args:
            query: 检索关键词。
            hits: 返回条数，上限 1000。
            first: 起始偏移量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "h": min(hits, 1000),
            "f": first,
        }

        resp = await self._client.get("/publ/api", params=params)
        data: dict[str, Any] = resp.json()

        result_obj = data.get("result", {})
        hits_obj = result_obj.get("hits", {})

        total_str = hits_obj.get("@total", "0")
        total = int(total_str) if total_str else 0

        hit_list = hits_obj.get("hit", [])
        if isinstance(hit_list, dict):
            hit_list = [hit_list]

        results = [self._parse_hit(h) for h in hit_list]

        return SearchResponse(
            query=query,
            total_results=total,
            page=(first // hits) + 1 if hits else 1,
            per_page=hits,
            results=results,
            source=SourceType.DBLP,
        )

    async def get_author(self, name: str) -> list[dict[str, Any]]:
        """搜索 DBLP 作者。

        Args:
            name: 作者姓名关键词。

        Returns:
            作者信息列表，每个元素包含 ``name``、``url``、``hit_count`` 等字段。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": name,
            "format": "json",
            "h": 10,
        }

        resp = await self._client.get("/author/api", params=params)
        data: dict[str, Any] = resp.json()

        result_obj = data.get("result", {})
        hits_obj = result_obj.get("hits", {})
        hit_list = hits_obj.get("hit", [])

        if isinstance(hit_list, dict):
            hit_list = [hit_list]

        authors: list[dict[str, Any]] = []
        for hit in hit_list:
            info = hit.get("info", {})
            authors.append(
                {
                    "name": info.get("author", ""),
                    "url": info.get("url", ""),
                    "notes": info.get("notes", {}),
                    "aliases": info.get("aliases", {}).get("alias", []),
                }
            )

        return authors
