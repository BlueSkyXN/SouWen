"""arXiv API 客户端

官方文档: https://info.arxiv.org/help/api/index.html
鉴权: 无需 Key
限流: 请求间隔 >= 3 秒
返回: Atom XML

文件用途：arXiv 预印本搜索客户端，提供高能物理、计算机科学等领域预印本服务。

函数/类清单：
    ArxivClient（类）
        - 功能：arXiv 预印本搜索客户端，解析 XML 格式响应为统一数据模型
        - 关键属性：_client (SouWenHttpClient) HTTP 客户端, _limiter (TokenBucketLimiter)
                   限流器（1 req / 3 sec）

    _text(element: ET.Element|None) -> str
        - 功能：安全提取 XML 元素文本，处理 None 和空值
        - 输入：element XML 元素或 None
        - 输出：元素文本（去首尾空白），元素为 None 时返回空字符串

    _parse_entry(entry: ET.Element) -> PaperResult
        - 功能：将 Atom XML entry 元素转换为 PaperResult 数据模型
        - 输入：entry arXiv API 返回的 <entry> XML 元素
        - 输出：统一的 PaperResult 模型，包含标题、作者、PDF 链接、分类等
        - 关键变量：arxiv_id (str) arXiv 唯一标识符, categories (list[str]) 学科分类

    search(query: str, id_list: list|None, start: int, max_results: int,
           sort_by: str|None, sort_order: str|None) -> SearchResponse
        - 功能：搜索 arXiv 论文或按 ID 列表查询
        - 输入：query 检索查询（支持字段前缀如 ti:/au:）, id_list arXiv ID 列表,
               start 起始偏移, max_results 返回条数（最多 2000）, sort_by/sort_order 排序参数
        - 输出：SearchResponse 包含结果列表及分页信息
        - 限流：通过 _limiter.acquire() 控制每 3 秒最多 1 次请求

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - defusedxml.ElementTree: 安全 XML 解析（防止 XXE 攻击）
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
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="arxiv")
        # 每 3 秒 1 次请求
        self._limiter = TokenBucketLimiter(rate=_RATE_LIMIT_RPS, burst=1.0)

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
        """安全提取 XML 元素文本。
        
        提取元素文本内容，自动处理 None 和空值情况。
        """
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
            # 提取并清理标题（可能包含换行符）
            title = cls._text(entry.find("atom:title", _NS))
            # arXiv 标题可能含换行，清理多余空白
            title = " ".join(title.split())

            # 提取并清理摘要
            summary = cls._text(entry.find("atom:summary", _NS))
            summary = " ".join(summary.split())

            # 提取作者列表及其所属机构
            authors: list[Author] = []
            for author_el in entry.findall("atom:author", _NS):
                name = cls._text(author_el.find("atom:name", _NS))
                # 机构信息存储在 arxiv:affiliation 子元素中
                affiliation_els = author_el.findall("arxiv:affiliation", _NS)
                affiliations = [cls._text(a) for a in affiliation_els if cls._text(a)]
                if name:
                    authors.append(
                        Author(
                            name=name,
                            affiliation="; ".join(affiliations) if affiliations else None,
                        )
                    )

            # 提取 arXiv ID：从 id 字段（格式：http://arxiv.org/abs/xxxx）提取纯 ID
            entry_id = cls._text(entry.find("atom:id", _NS))
            m = _ARXIV_ID_RE.search(entry_id)
            arxiv_id = m.group(1) if m else entry_id

            # 提取 PDF 链接及 HTML 链接
            pdf_url: str | None = None
            html_url: str | None = None
            for link in entry.findall("atom:link", _NS):
                rel = link.get("rel", "")
                link_type = link.get("type", "")
                href = link.get("href", "")
                # 优先使用 content-type 为 application/pdf 的链接
                if link_type == "application/pdf" or rel == "related":
                    if "pdf" in href:
                        pdf_url = href
                # 保留 alternate 链接作为源页面 URL
                if rel == "alternate":
                    html_url = href
            # 若未找到 PDF 链接，按 arXiv 命名规范构建
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

            # 提取 DOI（可选字段，部分论文无 DOI）
            doi_el = entry.find("arxiv:doi", _NS)
            doi = cls._text(doi_el) if doi_el is not None else None

            # 提取发表日期
            published = cls._text(entry.find("atom:published", _NS))
            year: int | None = None
            pub_date: str | None = None
            if published:
                pub_date = published[:10]  # 提取 YYYY-MM-DD 部分
                try:
                    year = int(published[:4])
                except ValueError:
                    pass

            # 提取学科分类标签
            categories: list[str] = []
            for cat in entry.findall("atom:category", _NS):
                term = cat.get("term", "")
                if term:
                    categories.append(term)

            # 提取论文评论（作者备注，可选）
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
                citation_count=None,  # arXiv 不提供引用数统计
                raw={
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

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ParseError(f"arXiv XML 解析失败: {exc}") from exc

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
            total_results=total,
            page=(start // max_results) + 1 if max_results else 1,
            per_page=max_results,
            results=results,
            source=SourceType.ARXIV,
        )
