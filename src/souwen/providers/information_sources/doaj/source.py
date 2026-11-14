"""doaj（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence, Mapping
from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.rate_limiter import TokenBucketLimiter
from souwen.config import get_config, SouWenConfig
from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    ClientSearchProvider,
    ClientSearchSpec,
)
from souwen.platform.provider_spec.models import AuthDeclaration, HttpOperation
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
from typing import Any, Protocol
from urllib.parse import quote


from souwen.platform.manifest_registry import ProviderManifest

DOAJ_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "doaj",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "doaj-search",
                "capability": "search",
                "export": "DoajSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "doaj-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["DOAJ_API_KEY"]},
        "network": {
            "egress_hosts": ["doaj.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["doaj-provider-config-v1"],
        },
    }
)


DOAJ_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="doaj",
    adapter_id="doaj-search",
    adapter_reason="encoded query path and article-id canonical URLs require a bridge",
    transport=ClientTransportDeclaration(
        host="doaj.org",
        base_path="/api",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/articles/"),),
    ),
    auth=AuthDeclaration(
        placement="header", reference="DOAJ_API_KEY", field_name="X-API-Key", required=False
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger(__name__)

_BASE_URL = "https://doaj.org/api"

_ARTICLE_URL = "https://doaj.org/article"

_RPS_WITH_KEY = 2.0

_RPS_WITHOUT_KEY = 1.0


class DoajClient:
    """DOAJ 开放获取期刊文章搜索客户端。

    特点:
        - 完全开放获取的同行评议期刊文章
        - API Key 可选，未配置时仍可使用（限流更严）
        - 返回 bibjson 元数据，包含 DOI、ISSN、关键词、主题等
        - 不提供引用计数
    """

    def __init__(self, api_key: str | None = None) -> None:
        """初始化 DOAJ 客户端。

        Args:
            api_key: DOAJ API Key（可选）。未提供时从全局配置读取，
                     仍未配置则匿名访问，限流更严格。
        """
        cfg = get_config()
        self.api_key: str | None = api_key or cfg.resolve_api_key("doaj", "doaj_api_key")

        headers: dict[str, str] = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        self._client = SouWenHttpClient(
            base_url=_BASE_URL,
            headers=headers,
            source_name="doaj",
        )
        rps = _RPS_WITH_KEY if self.api_key else _RPS_WITHOUT_KEY
        self._limiter = TokenBucketLimiter(rate=rps, burst=rps)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> DoajClient:
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
        """将 DOAJ 单条搜索结果转换为 PaperResult。

        DOAJ 响应结构：
        {
            "id": "...",
            "bibjson": {
                "title": "...",
                "author": [{"name": "..."}, ...],
                "abstract": "..." 或 {"text": "..."},
                "identifier": [{"type": "doi", "id": "10.xxx"}, ...],
                "year": "2024", "month": "3",
                "journal": {"title": "...", "issn": [...], ...},
                "keywords": [...],
                "subject": [{"term": "..."}, ...],
                "link": [{"type": "fulltext", "url": "..."}, ...]
            }
        }

        Args:
            item: DOAJ API 响应中的单条结果。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            bibjson: dict[str, Any] = item.get("bibjson", {}) or {}
            doaj_id: str = item.get("id", "")

            title: str = bibjson.get("title", "") or ""

            # 作者列表：[{"name": "..."}]
            authors: list[Author] = []
            for author_item in bibjson.get("author", []) or []:
                name = (
                    author_item.get("name", "")
                    if isinstance(author_item, dict)
                    else str(author_item)
                )
                if name:
                    authors.append(Author(name=name))

            # 摘要：可能是字符串，也可能是 {"text": "..."} 字典
            raw_abstract = bibjson.get("abstract")
            abstract: str | None = None
            if isinstance(raw_abstract, str):
                abstract = raw_abstract or None
            elif isinstance(raw_abstract, dict):
                abstract = raw_abstract.get("text") or None

            # DOI：在 identifier 列表中查找 type=="doi"
            doi: str | None = None
            for identifier in bibjson.get("identifier", []) or []:
                if isinstance(identifier, dict) and identifier.get("type", "").lower() == "doi":
                    doi = identifier.get("id")
                    break

            # 出版年/月
            year: int | None = None
            raw_year = bibjson.get("year")
            if raw_year:
                try:
                    year = int(str(raw_year)[:4])
                except (ValueError, TypeError):
                    pass

            pub_date: str | None = None
            raw_month = bibjson.get("month")
            if year:
                month_int = 1
                if raw_month:
                    try:
                        month_int = max(1, min(12, int(str(raw_month))))
                    except (ValueError, TypeError):
                        month_int = 1
                pub_date = f"{year:04d}-{month_int:02d}-01"

            # 期刊
            journal_obj = bibjson.get("journal") or {}
            journal_name: str | None = (
                journal_obj.get("title") if isinstance(journal_obj, dict) else None
            )

            # 链接：找 type=="fulltext"，按是否 .pdf 区分 pdf_url 和 source_url
            pdf_url: str | None = None
            fulltext_url: str | None = None
            for link in bibjson.get("link", []) or []:
                if not isinstance(link, dict):
                    continue
                if link.get("type", "").lower() != "fulltext":
                    continue
                url = link.get("url") or ""
                if not url:
                    continue
                if url.lower().endswith(".pdf"):
                    pdf_url = pdf_url or url
                else:
                    fulltext_url = fulltext_url or url

            # source_url：优先 fulltext 链接，否则用 DOAJ 文章页
            source_url: str = fulltext_url or (
                f"{_ARTICLE_URL}/{doaj_id}" if doaj_id else _ARTICLE_URL
            )

            # 主题：[{"term": "..."}]
            subjects: list[str] = []
            for subj in bibjson.get("subject", []) or []:
                if isinstance(subj, dict):
                    term = subj.get("term")
                    if term:
                        subjects.append(term)

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                journal=journal_name,
                source="doaj",  # type: ignore[arg-type]
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # DOAJ 不提供引用数
                raw={
                    "doaj_id": doaj_id,
                    "keywords": bibjson.get("keywords") or [],
                    "subject": subjects,
                    "issn": journal_obj.get("issn") if isinstance(journal_obj, dict) else None,
                    "publisher": journal_obj.get("publisher")
                    if isinstance(journal_obj, dict)
                    else None,
                    "country": journal_obj.get("country")
                    if isinstance(journal_obj, dict)
                    else None,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 DOAJ result 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        page_size: int = 10,
        page: int = 1,
    ) -> SearchResponse:
        """按关键词查询 DOAJ 文章索引。

        DOAJ 检索语法支持 Lucene 风格（field:value, AND/OR），
        简单关键词亦可。

        Args:
            query: 检索关键词或 Lucene 表达式。
            page_size: 每页条数。
            page: 当前页码（从 1 开始）。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        # DOAJ 将 query 直接编码到 URL path 中
        encoded_query = quote(query, safe="")
        path = f"/search/articles/{encoded_query}"
        params: dict[str, str | int] = {
            "page": page,
            "pageSize": page_size,
        }

        resp = await self._client.get(path, params=params)
        data: dict[str, Any] = resp.json()

        results_list = data.get("results", []) or []
        results: list[PaperResult] = []
        for item in results_list:
            try:
                results.append(self._parse_result(item))
            except ParseError as exc:
                logger.debug("跳过解析失败的 DOAJ 文章: %s", exc)

        return SearchResponse(
            query=query,
            total_results=data.get("total", len(results)),
            page=page,
            per_page=page_size,
            results=results,
            source="doaj",  # type: ignore[arg-type]
        )


_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class DoajClientProtocol(Protocol):
    async def search(self, query: str, page_size: int = 10, page: int = 1) -> Any: ...


class DoajSearchProvider(ClientSearchProvider):
    def __init__(self, client: DoajClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, page_size=limit, page=1)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "doaj"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid DOAJ response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("doaj",), succeeded=("doaj",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = getattr(paper, "raw", {}).get("doaj_id")
    if (
        getattr(paper, "source", None) != "doaj"
        or not isinstance(identifier, str)
        or _ID.fullmatch(identifier) is None
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid DOAJ item")
    return SearchItem(
        id=f"doaj:{identifier}",
        title=paper.title.strip(),
        url=f"https://doaj.org/article/{identifier}",
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="doaj", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme="doaj", value=identifier),),
        ),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid year")
    return value


def _authors(paper: Any) -> tuple[str, ...]:
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(paper, "authors", ())
    )
    if any(author is None for author in authors) or len(set(authors)) != len(authors):
        raise ValueError("invalid authors")
    return tuple(author for author in authors if author is not None)


_SPEC = ClientSearchSpec("doaj", "paper", _invoke, _project)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return DoajSearchProvider(
        DoajClient(api_key=secrets.get("DOAJ_API_KEY")),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = DOAJ_PROVIDER_MANIFEST
SPEC = DOAJ_PROVIDER_SPEC
PROVIDER_TYPE = DoajSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
