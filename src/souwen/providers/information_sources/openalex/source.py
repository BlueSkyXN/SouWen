"""openalex（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from souwen.common_runtime.provider_support.exceptions import NotFoundError, ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.provider_support.parsing import safe_parse_date
from souwen.common_runtime.resilience import TokenBucketLimiter
from souwen.config import get_config, SouWenConfig
from souwen.platform.provider_spec import (
    RestJsonProviderSpec,
    ClientSearchProvider,
    ClientSearchSpec,
)
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
from urllib.parse import urlsplit


from souwen.platform.manifest_registry import ProviderManifest


OPENALEX_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "openalex",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "openalex-search",
                "capability": "search",
                "export": "OpenAlexSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "openalex-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        # OpenAlex has anonymous access. An API key raises quota but is not a
        # required v2 secret reference and therefore cannot make it ineligible.
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.openalex.org"],
            "min_egress": "impersonate",
            "max_egress": "proxy",
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["openalex-provider-config-v1"],
        },
    }
)


__all__ = ["OPENALEX_PROVIDER_MANIFEST"]


OPENALEX_REST_SPEC = RestJsonProviderSpec(
    provider_id="openalex",
    adapter_id="openalex-search",
    adapter_kind="client_adapter",
    review_status="reviewed_adapter",
    adapter_reason="existing filter and DOI fallback projection require a reviewed mapping migration",
    host="api.openalex.org",
    base_path="/works",
    configuration_keys=("enabled",),
)

__all__ = ["OPENALEX_REST_SPEC"]


logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org"

_DEFAULT_RPS = 10.0


class OpenAlexClient:
    """OpenAlex 论文搜索客户端。

    Attributes:
        api_key: OpenAlex API Key，可选；配置后获得更高每日预算。
        mailto: 已弃用兼容字段；继续接受但不再发送给 OpenAlex。
    """

    def __init__(self, mailto: str | None = None, *, api_key: str | None = None) -> None:
        """初始化 OpenAlex 客户端。

        Args:
            mailto: 已弃用兼容字段。未提供时仍从全局配置读取，但不会发送给上游。
            api_key: OpenAlex API Key。未提供时按 source channel、flat config 顺序读取。
        """
        cfg = get_config()
        self.api_key: str | None = api_key or cfg.resolve_api_key("openalex", "openalex_api_key")
        self.mailto: str | None = mailto or cfg.openalex_email
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="openalex")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> OpenAlexClient:
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

    def _common_params(self) -> dict[str, str]:
        """构建公共请求参数。

        ``api_key`` 是当前 OpenAlex 的认证/预算参数。已弃用的 ``mailto`` 继续
        作为构造器和配置属性保留，但当前官方契约未列出该参数，因此不再发送。
        """
        params: dict[str, str] = {}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @staticmethod
    def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
        """从倒排索引重建摘要文本。

        OpenAlex 以 ``{word: [positions]}`` 的形式存储摘要，
        需要按位置还原为连续文本。

        Args:
            inverted_index: OpenAlex 返回的 abstract_inverted_index。

        Returns:
            还原后的摘要纯文本；若输入为空则返回空字符串。
        """
        if not inverted_index:
            return ""
        # 展开为 (position, word) 元组列表
        position_word: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            for pos in positions:
                position_word.append((pos, word))
        # 按位置排序
        position_word.sort(key=lambda x: x[0])
        # 拼接为连续文本
        return " ".join(w for _, w in position_word)

    def _parse_work(self, work: dict[str, Any]) -> PaperResult:
        """将 OpenAlex Work 对象转换为 PaperResult。

        Args:
            work: OpenAlex API 返回的单条 work JSON。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 关键字段缺失或格式异常。
        """
        try:
            # 提取作者列表及其所属机构
            authors: list[Author] = []
            for authorship in work.get("authorships", []):
                author_obj = authorship.get("author", {})
                # 提取该作者的所有机构名称并用分号连接
                authors.append(
                    Author(
                        name=author_obj.get("display_name", ""),
                        affiliation="; ".join(
                            inst.get("display_name", "")
                            for inst in authorship.get("institutions", [])
                            if inst.get("display_name")
                        )
                        or None,
                    )
                )

            # 提取 DOI 并去除 URL 前缀（OpenAlex 返回完整 DOI URL）
            raw_doi: str | None = work.get("doi")
            doi: str | None = None
            if raw_doi:
                # 去除常见的 DOI URL 前缀，提取纯 DOI
                doi = raw_doi.replace("https://doi.org/", "").replace("http://doi.org/", "")

            # 从倒排索引重建摘要
            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))

            # 提取出版年份和日期
            pub_year: int | None = work.get("publication_year")
            pub_date = safe_parse_date(work.get("publication_date"))

            # 提取最佳 OA PDF 链接（OpenAlex 会自动选择最佳 OA 来源）
            best_oa = work.get("best_oa_location") or {}
            pdf_url: str | None = best_oa.get("pdf_url")

            # 提取发表期刊/会议名称
            primary_loc = work.get("primary_location") or {}
            source_info = primary_loc.get("source") or {}
            journal_name: str | None = source_info.get("display_name") or None

            return PaperResult(
                title=work.get("display_name", work.get("title", "")),
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=pub_year,
                publication_date=pub_date,
                source="openalex",
                source_url=work.get("id", ""),
                pdf_url=pdf_url,
                citation_count=work.get("cited_by_count"),
                journal=journal_name,
                raw={
                    "type": work.get("type"),
                    "is_oa": work.get("open_access", {}).get("is_oa"),
                    # 取前 5 个主要研究概念
                    "concepts": [c.get("display_name") for c in work.get("concepts", [])[:5]],
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 OpenAlex work 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> SearchResponse:
        """全文搜索论文。

        Args:
            query: 检索关键词。
            filters: OpenAlex filter 参数，如 ``{"from_publication_date": "2023-01-01"}``。
            sort: 排序字段，如 ``"cited_by_count:desc"``。
            page: 页码（从 1 开始）。
            per_page: 每页条数，上限 200。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params = self._common_params()
        params["search"] = query
        params["page"] = str(page)
        params["per_page"] = str(min(per_page, 200))

        if filters:
            filter_parts = [f"{k}:{v}" for k, v in filters.items()]
            params["filter"] = ",".join(filter_parts)
        if sort:
            params["sort"] = sort

        resp = await self._client.get("/works", params=params)
        data: dict[str, Any] = resp.json()

        results = [self._parse_work(w) for w in data.get("results", [])]
        meta = data.get("meta", {})

        return SearchResponse(
            query=query,
            total_results=meta.get("count", len(results)),
            page=page,
            per_page=per_page,
            results=results,
            source="openalex",
        )

    async def get_by_doi(self, doi: str) -> PaperResult:
        """通过 DOI 获取论文详情。

        Args:
            doi: 论文 DOI，例如 ``"10.1038/s41586-021-03819-2"``。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: DOI 不存在。
        """
        await self._limiter.acquire()
        params = self._common_params()

        resp = await self._client.get(f"/works/https://doi.org/{doi}", params=params)
        if resp.status_code == 404:
            raise NotFoundError(f"OpenAlex 未找到 DOI: {doi}")

        return self._parse_work(resp.json())

    async def get_by_id(self, openalex_id: str) -> PaperResult:
        """通过 OpenAlex ID 获取论文详情。

        Args:
            openalex_id: OpenAlex 标识，如 ``"W2741809807"`` 或完整 URL。

        Returns:
            PaperResult 模型。

        Raises:
            NotFoundError: ID 不存在。
        """
        await self._limiter.acquire()
        params = self._common_params()

        # 支持短 ID 或完整 URL
        if openalex_id.startswith("http"):
            url = openalex_id
        else:
            url = f"/works/{openalex_id}"

        resp = await self._client.get(url, params=params)
        if resp.status_code == 404:
            raise NotFoundError(f"OpenAlex 未找到 ID: {openalex_id}")

        return self._parse_work(resp.json())


_PROVIDER_ID = "openalex"


class OpenAlexClientProtocol(Protocol):
    """The minimal existing-client surface used by this target adapter."""

    async def search(
        self,
        query: str,
        filters: dict[str, str] | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 10,
    ) -> Any:
        """Return a existing ``SearchResponse`` compatible object."""


class OpenAlexSearchProvider(ClientSearchProvider):
    """Search-only provider that preserves existing OpenAlex query behavior behind the SPI."""

    capability = "search"

    def __init__(self, client: OpenAlexClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _OPENALEX_BRIDGE_SPEC, enabled=enabled)


def _existing_filters(request: SearchRequest) -> dict[str, str] | None:
    """Map only canonical, reviewed filters in deterministic upstream parameter order."""
    if request.filters is None:
        return None
    filters: dict[str, str] = {}
    if request.filters.year_from is not None:
        filters["from_publication_date"] = f"{request.filters.year_from:04d}-01-01"
    if request.filters.year_to is not None:
        filters["to_publication_date"] = f"{request.filters.year_to:04d}-12-31"
    if request.filters.language is not None:
        filters["language"] = request.filters.language
    if request.filters.open_access is not None:
        filters["is_oa"] = "true" if request.filters.open_access else "false"
    if request.filters.resource_type is not None:
        filters["type"] = request.filters.resource_type
    return filters or None


def _to_search_page(response: Any, *, limit: int, context: RequestContext) -> SearchPage:
    """Strictly transform existing ``SearchResponse`` / ``PaperResult`` data to canonical DTOs."""
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing response source")
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    response_page = getattr(response, "page", None)
    response_limit = getattr(response, "per_page", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid existing search results")
    if total is not None and (not isinstance(total, int) or isinstance(total, bool) or total < 0):
        raise ValueError("invalid existing result total")
    if response_page != 1 or response_limit != limit:
        raise ValueError("existing page does not match canonical request")

    items = tuple(
        _to_search_item(paper, rank=index) for index, paper in enumerate(results, start=1)
    )
    return SearchPage(
        items=items,
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _to_search_item(paper: Any, *, rank: int) -> SearchItem:
    """Map one normalized existing paper while retaining only canonical public metadata."""
    if getattr(paper, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing paper source")
    title = _required_text(getattr(paper, "title", None))
    doi = _normalise_doi(getattr(paper, "doi", None))
    source_url = _normalise_url(getattr(paper, "source_url", None))
    if doi is None and source_url is None:
        raise ValueError("paper lacks stable identifier")

    identifiers: list[SearchIdentifier] = []
    if doi is not None:
        identifiers.append(SearchIdentifier(scheme="doi", value=doi))
    if source_url is not None:
        identifiers.append(SearchIdentifier(scheme="openalex", value=source_url))
    item_id = f"doi:{doi.lower()}" if doi is not None else f"openalex:{source_url}"
    canonical_url = f"https://doi.org/{doi}" if doi is not None else source_url
    raw = getattr(paper, "raw", {})
    if not isinstance(raw, Mapping):
        raise ValueError("invalid existing paper attributes")

    return SearchItem(
        id=item_id,
        title=title,
        url=canonical_url,
        snippet=_optional_text(getattr(paper, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_optional_int(getattr(paper, "year", None)),
            authors=_author_names(getattr(paper, "authors", None)),
            identifiers=tuple(identifiers),
            resource_type=_optional_text(raw.get("type")),
            open_access=raw.get("is_oa") if isinstance(raw.get("is_oa"), bool) else None,
            citation_count=_optional_nonnegative_int(getattr(paper, "citation_count", None)),
        ),
    )


def _required_text(value: Any) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise ValueError("missing required text")
    return normalized


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid text")
    normalized = value.strip()
    return normalized or None


def _normalise_doi(value: Any) -> str | None:
    doi = _optional_text(value)
    if doi is None:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix) :]
            break
    doi = _required_text(doi)
    prefix, separator, suffix = doi.partition("/")
    if not separator or not prefix.startswith("10.") or not prefix[3:].isdigit() or not suffix:
        raise ValueError("invalid DOI")
    if any(character.isspace() for character in doi):
        raise ValueError("invalid DOI")
    return doi


def _normalise_url(value: Any) -> str | None:
    url = _optional_text(value)
    if url is None:
        return None
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "openalex.org"
        or not parsed.path.startswith("/W")
    ):
        raise ValueError("invalid OpenAlex source URL")
    return url


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 9999:
        raise ValueError("invalid year")
    return value


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("invalid citation count")
    return value


def _author_names(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("invalid authors")
    names: list[str] = []
    for author in value:
        name = _required_text(getattr(author, "name", None))
        if name not in names:
            names.append(name)
    return tuple(names)


async def _bridge_invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(
        request.query, filters=_existing_filters(request), sort=None, page=1, per_page=limit
    )


def _bridge_project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    return _to_search_page(response, limit=limit, context=context)


_OPENALEX_BRIDGE_SPEC = ClientSearchSpec(
    "openalex", "paper", _bridge_invoke, _bridge_project, accepts_filters=True
)

__all__ = ["OpenAlexClientProtocol", "OpenAlexSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del configuration, secrets, reviewed_proxy
    return OpenAlexSearchProvider(
        OpenAlexClient(api_key=config.resolve_api_key("openalex", "openalex_api_key")),
        enabled=True,
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("openalex", default=True):
        raise ValueError("provider is disabled")
    return {"enabled": True}


MANIFEST = OPENALEX_PROVIDER_MANIFEST
SPEC = OPENALEX_REST_SPEC
PROVIDER_TYPE = OpenAlexSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
