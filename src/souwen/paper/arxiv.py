"""arXiv API 客户端

官方文档: https://info.arxiv.org/help/api/index.html
鉴权: 无需 Key
限流: 请求间隔 >= 3 秒
返回: Atom XML
"""

from __future__ import annotations

import logging
import re
import defusedxml.ElementTree as ET
from typing import Any

from souwen.exceptions import ParseError
from souwen.http_client import SouWenHttpClient
from souwen.models import Author, PaperResult, SearchResponse, SourceType
from souwen.rate_limiter import TokenBucketLimiter

logger = logging.getLogger(__name__)

_BASE_URL = "http://export.arxiv.org/api"

# arXiv 要求至少 3 秒间隔
_RATE_LIMIT_RPS = 1.0 / 3.0

# Atom XML 命名空间
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    "arxiv": "http://arxiv.org/schemas/atom",
}

# 从 arXiv ID URL 提取纯 ID 的正则
_ARXIV_ID_RE = re.compile(r"abs/(.+)$")


class ArxivClient:
    """arXiv 预印本搜索客户端。

    特点:
        - 所有论文均可获取 PDF 链接
        - 返回 Atom XML 格式，内部解析为统一模型
    """

    def __init__(self) -> None:
        """初始化 arXiv 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL)
        # 每 3 秒 1 次请求
        self._limiter = TokenBucketLimiter(
            rate=_RATE_LIMIT_RPS, burst=1.0
        )

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ArxivClient:
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
    def _text(element: ET.Element | None) -> str:
        """安全提取 XML 元素文本。"""
        return (element.text or "").strip() if element is not None else ""

    @classmethod
    def _parse_entry(cls, entry: ET.Element) -> PaperResult:
        """将 Atom entry 元素转换为 PaperResult。

        Args:
            entry: XML ``<entry>`` 元素。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析失败。
        """
        try:
            title = cls._text(entry.find("atom:title", _NS))
            # arXiv 标题可能含换行，清理空白
            title = " ".join(title.split())

            summary = cls._text(entry.find("atom:summary", _NS))
            summary = " ".join(summary.split())

            # 作者列表
            authors: list[Author] = []
            for author_el in entry.findall("atom:author", _NS):
                name = cls._text(author_el.find("atom:name", _NS))
                affiliation_els = author_el.findall("arxiv:affiliation", _NS)
                affiliations = [cls._text(a) for a in affiliation_els if cls._text(a)]
                if name:
                    authors.append(Author(
                        name=name,
                        affiliation="; ".join(affiliations) if affiliations else None,
                    ))

            # ID & 链接
            entry_id = cls._text(entry.find("atom:id", _NS))
            m = _ARXIV_ID_RE.search(entry_id)
            arxiv_id = m.group(1) if m else entry_id

            # PDF 链接
            pdf_url: str | None = None
            html_url: str | None = None
            for link in entry.findall("atom:link", _NS):
                rel = link.get("rel", "")
                link_type = link.get("type", "")
                href = link.get("href", "")
                if link_type == "application/pdf" or rel == "related":
                    if "pdf" in href:
                        pdf_url = href
                if rel == "alternate":
                    html_url = href
            # arXiv PDF 链接遵循固定模式
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

            # DOI (部分论文有)
            doi_el = entry.find("arxiv:doi", _NS)
            doi = cls._text(doi_el) if doi_el is not None else None

            # 发表日期
            published = cls._text(entry.find("atom:published", _NS))
            year: int | None = None
            pub_date: str | None = None
            if published:
                pub_date = published[:10]  # YYYY-MM-DD
                try:
                    year = int(published[:4])
                except ValueError:
                    pass

            # 分类
            categories: list[str] = []
            for cat in entry.findall("atom:category", _NS):
                term = cat.get("term", "")
                if term:
                    categories.append(term)

            # 评论
            comment_el = entry.find("arxiv:comment", _NS)
            comment = cls._text(comment_el) if comment_el is not None else None

            return PaperResult(
                title=title,
                authors=authors,
                abstract=summary,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source=SourceType.ARXIV,
                source_url=html_url or f"https://arxiv.org/abs/{arxiv_id}",
                pdf_url=pdf_url,
                citation_count=None,  # arXiv 不提供引用数
                extra={
                    "categories": categories,
                    "primary_category": categories[0] if categories else None,
                    "comment": comment,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 arXiv entry 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        id_list: list[str] | None = None,
        start: int = 0,
        max_results: int = 10,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> SearchResponse:
        """搜索 arXiv 论文。

        Args:
            query: arXiv 搜索查询，支持字段前缀如 ``ti:``、``au:``。
                   若 id_list 非空且 query 为空，则按 ID 列表检索。
            id_list: arXiv ID 列表，如 ``["2301.00001", "2301.00002"]``。
            start: 起始偏移量。
            max_results: 返回条数，上限 2000 (API 建议 <= 1000)。
            sort_by: 排序字段: ``"relevance"``、``"lastUpdatedDate"``、
                     ``"submittedDate"``。
            sort_order: ``"ascending"`` 或 ``"descending"``。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "start": start,
            "max_results": min(max_results, 2000),
        }

        if query:
            params["search_query"] = query
        if id_list:
            params["id_list"] = ",".join(id_list)
        if sort_by:
            params["sortBy"] = sort_by
        if sort_order:
            params["sortOrder"] = sort_order

        resp = await self._client.get("/query", params=params)
        xml_text = resp.text

        root = ET.fromstring(xml_text)

        # 总数
        total_el = root.find("opensearch:totalResults", _NS)
        total = int(self._text(total_el)) if total_el is not None else 0

        entries = root.findall("atom:entry", _NS)
        results: list[PaperResult] = []
        for entry in entries:
            # arXiv 在无结果时返回一个空 entry，需跳过
            title = self._text(entry.find("atom:title", _NS))
            if not title or title == "Error":
                continue
            results.append(self._parse_entry(entry))

        return SearchResponse(
            query=query or ",".join(id_list or []),
            total=total,
            page=(start // max_results) + 1 if max_results else 1,
            per_page=max_results,
            results=results,
            source=SourceType.ARXIV,
        )
