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
        - raw 字段：categories, primary_category, comment, journal_ref,
                   updated（最后修订日期）, version（版本号，如 "v2"）

    _build_search_query(query: str, categories: list[str]|None, date_from: str|None,
                        date_to: str|None) -> str
        - 功能：组合用户查询、学科分类、提交日期范围，生成 arXiv 检索字符串
        - 输入：query 原始查询；categories 分类列表（如 ["cs.AI", "cs.LG"]）；
               date_from/date_to 日期 YYYY-MM-DD
        - 输出：完整的 search_query 字符串，已按 arXiv 语法拼接

    search(query: str, id_list: list|None, start: int, max_results: int,
           sort_by: str|None, sort_order: str|None,
           categories: list[str]|None, date_from: str|None,
           date_to: str|None) -> SearchResponse
        - 功能：搜索 arXiv 论文或按 ID 列表查询，支持分类与日期范围过滤
        - 输入：query 检索查询（支持字段前缀如 ti:/au:）, id_list arXiv ID 列表,
               start 起始偏移, max_results 返回条数（最多 2000）, sort_by/sort_order 排序参数,
               categories 学科分类过滤, date_from/date_to 提交日期范围过滤
        - 输出：SearchResponse 包含结果列表及分页信息
        - 限流：通过 _limiter.acquire() 控制每 3 秒最多 1 次请求
        - 注意：含日期过滤时直接拼接 URL 字符串，避免 httpx 把 ``+TO+`` 编码为
               ``%2BTO%2B``（arXiv 要求字面 ``+`` 字符）

    search_all(query: str, id_list: list|None, sort_by: str|None,
               sort_order: str|None, categories: list[str]|None,
               date_from: str|None, date_to: str|None,
               batch_size: int) -> AsyncIterator[PaperResult]
        - 功能：无限分页异步迭代器，逐批获取所有匹配结果
        - 输入：与 search() 相同（无 start/max_results），batch_size 每批请求数量（默认 100）
        - 输出：AsyncIterator[PaperResult]，逐条 yield
        - 说明：自动根据 total_results 决定何时停止，比 search() 更适合大批量获取

模块依赖：
    - SouWenHttpClient: 统一 HTTP 客户端
    - TokenBucketLimiter: 令牌桶限流器
    - defusedxml.ElementTree: 安全 XML 解析（防止 XXE 攻击）
"""

from __future__ import annotations

import logging
import re
import defusedxml.ElementTree as ET
from typing import Any, AsyncIterator

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
# 从 arXiv ID 提取版本号（如 "2301.00001v2" 中的 "v2"）
_ARXIV_VERSION_RE = re.compile(r"v(\d+)$")


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

            # 提取期刊引用（部分论文在接受后会填写此字段，如 "Phys.Rev.Lett. 120 (2018) 161601"）
            journal_ref_el = entry.find("arxiv:journal_ref", _NS)
            journal_ref = cls._text(journal_ref_el) if journal_ref_el is not None else None

            # 提取最后修订日期（<updated> 与 <published> 不同，表示最近一次版本更新时间）
            updated = cls._text(entry.find("atom:updated", _NS))
            updated_date: str | None = updated[:10] if updated else None

            # 从 arXiv ID 中提取版本号（如 "2301.00001v2" → "v2"）
            vm = _ARXIV_VERSION_RE.search(arxiv_id)
            version = vm.group(0) if vm else None

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
                    "journal_ref": journal_ref,
                    "updated": updated_date,
                    "version": version,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 arXiv entry 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    @staticmethod
    def _build_search_query(
        query: str,
        categories: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> str:
        """组合查询、分类与日期，生成 arXiv ``search_query`` 字符串。

        - 多个分类以 ``OR`` 连接，整体以 ``AND`` 拼接到原 query。
        - 日期范围使用 ``submittedDate:[YYYYMMDD0000+TO+YYYYMMDD2359]`` 语法。
          其中 ``+TO+`` 为字面 ``+`` 字符，调用方需绕过 URL 编码。
        - 仅缺省 ``date_from`` 时使用 ``00000101``，仅缺省 ``date_to`` 时使用 ``99991231``。
        """
        parts: list[str] = []
        if query:
            # 含空格/括号时已由调用方控制是否加括号；此处只要存在原 query 就保留
            parts.append(f"({query})" if (categories or date_from or date_to) and query else query)

        if categories:
            cat_clause = " OR ".join(f"cat:{c}" for c in categories)
            parts.append(f"({cat_clause})")

        if date_from or date_to:
            start_compact = (date_from or "0000-01-01").replace("-", "") + "0000"
            end_compact = (date_to or "9999-12-31").replace("-", "") + "2359"
            # ``+TO+`` 使用字面 ``+``，外层调用方需通过手工拼接 URL 避免被编码
            parts.append(f"submittedDate:[{start_compact}+TO+{end_compact}]")

        return " AND ".join(parts)

    async def search(
        self,
        query: str,
        id_list: list[str] | None = None,
        start: int = 0,
        max_results: int = 10,
        sort_by: str | None = None,
        sort_order: str | None = None,
        categories: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
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
            categories: 学科分类过滤列表，如 ``["cs.AI", "cs.LG"]``，多个分类间以
                        ``OR`` 连接后 ``AND`` 到原查询。
            date_from: 起始日期 ``YYYY-MM-DD`` 格式（按 submittedDate 过滤）。
            date_to: 结束日期 ``YYYY-MM-DD`` 格式。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        # 组合查询字符串：基础 query + 分类过滤 + 日期范围
        effective_query = self._build_search_query(query, categories, date_from, date_to)
        has_date_filter = bool(date_from or date_to)

        capped_max = min(max_results, 2000)

        if has_date_filter:
            # 日期过滤含 ``+TO+`` 字面 ``+``，httpx 会将 ``+`` URL 编码为 ``%2B``，
            # 因此手工拼接 URL 字符串绕过 params 编码。其余参数仍按原样附加。
            url_parts: list[str] = [f"search_query={effective_query}"]
            if id_list:
                url_parts.append(f"id_list={','.join(id_list)}")
            url_parts.append(f"start={start}")
            url_parts.append(f"max_results={capped_max}")
            if sort_by:
                url_parts.append(f"sortBy={sort_by}")
            if sort_order:
                url_parts.append(f"sortOrder={sort_order}")
            full_url = "/query?" + "&".join(url_parts)
            resp = await self._client.get(full_url)
        else:
            params: dict[str, str | int] = {
                "start": start,
                "max_results": capped_max,
            }
            if effective_query:
                params["search_query"] = effective_query
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

    async def search_all(
        self,
        query: str,
        id_list: list[str] | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        categories: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        batch_size: int = 100,
    ) -> AsyncIterator[PaperResult]:
        """无限分页异步迭代器，获取所有匹配的 arXiv 论文。

        与 search() 不同，本方法不限制返回数量，自动分批请求直到取尽所有结果。
        适合大批量数据采集场景（对应 arxiv.py 的 ``max_results=None`` 行为）。

        Args:
            query: arXiv 搜索查询，支持字段前缀如 ``ti:``、``au:``。
            id_list: arXiv ID 列表，如 ``["2301.00001", "2301.00002"]``。
            sort_by: 排序字段: ``"relevance"``、``"lastUpdatedDate"``、
                     ``"submittedDate"``。
            sort_order: ``"ascending"`` 或 ``"descending"``。
            categories: 学科分类过滤列表，如 ``["cs.AI", "cs.LG"]``。
            date_from: 起始日期 ``YYYY-MM-DD`` 格式。
            date_to: 结束日期 ``YYYY-MM-DD`` 格式。
            batch_size: 每次 API 请求的批量大小（默认 100，上限 2000）。

        Yields:
            PaperResult：逐条返回论文结果。

        Note:
            - 每批请求受速率限制（3 秒间隔），大批量采集请注意时间成本。
            - 当 API 返回结果数少于 batch_size 时，迭代自动终止。
        """
        batch = min(batch_size, 2000)
        start = 0
        seen = 0
        total_known: int | None = None

        while True:
            response = await self.search(
                query=query,
                id_list=id_list,
                start=start,
                max_results=batch,
                sort_by=sort_by,
                sort_order=sort_order,
                categories=categories,
                date_from=date_from,
                date_to=date_to,
            )

            if total_known is None:
                total_known = response.total_results

            for paper in response.results:
                yield paper
                seen += 1

            # 当本批次无结果或已取尽所有结果时停止
            if not response.results:
                break
            if total_known is not None and seen >= total_known:
                break

            start += batch
