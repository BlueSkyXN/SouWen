"""arXiv 论文搜索源（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

import defusedxml.ElementTree as ET

from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter
from souwen.config import SouWenConfig
from souwen.platform.manifest_registry import ProviderManifest
from souwen.platform.provider_spec import (
    ClientSearchProvider,
    ClientSearchProviderSpec,
    ClientSearchSpec,
    ClientTransportDeclaration,
)
from souwen.platform.provider_spec.models import HttpOperation
from souwen.platform.provider_spi import (
    PageInfo,
    Provenance,
    RequestContext,
    SearchAttributes,
    SearchIdentifier,
    SearchItem,
    SearchMeta,
    SearchPage,
    SearchRequest,
)
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse

logger = logging.getLogger(__name__)

ARXIV_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "arxiv",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "arxiv-search",
                "capability": "search",
                "export": "ArxivSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "arxiv-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["export.arxiv.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["arxiv-provider-config-v1"],
        },
    }
)

ARXIV_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="arxiv",
    adapter_id="arxiv-search",
    adapter_reason="existing client parses Atom XML and preserves reviewed query construction",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="export.arxiv.org",
        base_path="/api",
        protocol="atom_xml",
        operations=(HttpOperation(method="GET", endpoint="/query"),),
    ),
    configuration_keys=("enabled",),
)

_BASE_URL = "https://export.arxiv.org/api"

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

# arXiv 标识符：新式 2501.12345 / 旧式 hep-th/9901001，均允许 vN 版本后缀。
_ID = re.compile(r"^(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})(?:v\d+)?$")


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
                source="arxiv",
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
            source="arxiv",
        )


class ArxivClientProtocol(Protocol):
    async def search(self, query: str, max_results: int = 10) -> Any: ...


class ArxivSearchProvider(ClientSearchProvider):
    def __init__(self, client: ArxivClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, max_results=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = _response_items(response, limit)
    items = tuple(_item(paper, index) for index, paper in enumerate(results, 1))
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, total=response.total_results),
        meta=SearchMeta(requested=("arxiv",), succeeded=("arxiv",)),
        context=context,
    )


def _response_items(response: Any, limit: int) -> Sequence[Any]:
    results = getattr(response, "results", None)
    if (
        getattr(response, "source", None) != "arxiv"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
    ):
        raise ValueError("invalid arXiv response")
    total = getattr(response, "total_results", None)
    if not isinstance(total, int) or isinstance(total, bool) or total < len(results):
        raise ValueError("invalid arXiv total")
    return results


def _item(paper: Any, rank: int) -> SearchItem:
    if (
        getattr(paper, "source", None) != "arxiv"
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid arXiv item")
    parsed = urlsplit(getattr(paper, "source_url", ""))
    match = re.fullmatch(r"/abs/(.+)", parsed.path)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"arxiv.org", "www.arxiv.org"}
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
        or match is None
        or _ID.fullmatch(match.group(1)) is None
    ):
        raise ValueError("invalid arXiv identifier")
    identifier = match.group(1)
    return SearchItem(
        id=f"arxiv:{identifier}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="arxiv", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="arxiv", value=identifier),),
        ),
    )


_SPEC = ClientSearchSpec("arxiv", "paper", _invoke, _project)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无代理通道
    return ArxivSearchProvider(ArxivClient(), enabled=bool(configuration["enabled"]))


MANIFEST = ARXIV_PROVIDER_MANIFEST
SPEC = ARXIV_PROVIDER_SPEC
PROVIDER_TYPE = ArxivSearchProvider

__all__ = [
    "ARXIV_PROVIDER_MANIFEST",
    "ARXIV_PROVIDER_SPEC",
    "ArxivClient",
    "ArxivSearchProvider",
    "MANIFEST",
    "PROVIDER_TYPE",
    "SPEC",
    "build_provider",
]
