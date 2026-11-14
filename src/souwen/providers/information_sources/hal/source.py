"""hal（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

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
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import (
    ClientSearchProviderSpec,
    ClientTransportDeclaration,
    ClientSearchProvider,
    ClientSearchSpec,
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
from typing import Any, Protocol
from urllib.parse import urlsplit


from souwen.platform.manifest_registry import ProviderManifest

HAL_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "hal",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "hal-search",
                "capability": "search",
                "export": "HalSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "hal-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.archives-ouvertes.fr"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["hal-provider-config-v1"],
        },
    }
)


HAL_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="hal",
    adapter_id="hal-search",
    review_status="reviewed_adapter",
    adapter_reason="existing HAL URLs use more than one reviewed record host and array normalization",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="api.archives-ouvertes.fr",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/search/"),),
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger(__name__)

_BASE_URL = "https://api.archives-ouvertes.fr"

_DEFAULT_RPS = 5.0

_FIELDS = ",".join(
    [
        "halId_s",
        "title_s",
        "authFullName_s",
        "abstract_s",
        "doiId_s",
        "producedDateY_i",
        "submittedDate_s",
        "linkExtUrl_s",
        "fileMain_s",
        "uri_s",
        "docType_s",
        "journalTitle_s",
    ]
)


def _first(value: Any) -> Any:
    """HAL Solr 多数字段为数组，统一取首元素。

    Args:
        value: 任意值（可能是 list / 标量 / None）。

    Returns:
        若为非空 list 返回第一个元素；否则原样返回。
    """
    if isinstance(value, list):
        return value[0] if value else None
    return value


class HalClient:
    """HAL 法国开放档案检索客户端。

    特点:
        - 基于 Solr，支持丰富的查询语法（字段限定、布尔、范围等）
        - 字段以后缀标识类型：_s 字符串、_i 整数、_t 文本
        - 无需 API Key，零配置即用
        - fileMain_s 直接给出 PDF URL
    """

    def __init__(self) -> None:
        """初始化 HAL 客户端。"""
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="hal")
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> HalClient:
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
    def _parse_doc(doc: dict[str, Any]) -> PaperResult:
        """将 HAL Solr response.docs 中的单条记录转换为 PaperResult。

        Args:
            doc: HAL Solr 响应中的单条文献对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            hal_id: str = _first(doc.get("halId_s")) or ""
            title: str = _first(doc.get("title_s")) or ""
            abstract: str = _first(doc.get("abstract_s")) or ""

            # 作者：authFullName_s 已是全名列表
            raw_authors = doc.get("authFullName_s") or []
            if isinstance(raw_authors, str):
                raw_authors = [raw_authors]
            authors: list[Author] = [
                Author(name=name) for name in raw_authors if name and isinstance(name, str)
            ]

            # DOI：HAL 中通常已是字符串，少数情况下也可能为列表
            doi_raw = doc.get("doiId_s")
            doi: str | None = _first(doi_raw) if isinstance(doi_raw, list) else doi_raw
            if doi == "":
                doi = None

            # 年份：producedDateY_i 是整数年份
            year_raw = doc.get("producedDateY_i")
            year: int | None
            if isinstance(year_raw, list):
                year_raw = year_raw[0] if year_raw else None
            try:
                year = int(year_raw) if year_raw is not None else None
            except (TypeError, ValueError):
                year = None

            # 提交日期：submittedDate_s 形如 "2024-01-15 10:00:00" 或 ISO 字符串
            submitted = _first(doc.get("submittedDate_s"))
            pub_date: str | None = None
            if isinstance(submitted, str) and submitted:
                # 取前 10 位（YYYY-MM-DD）即可，PaperResult 校验器会容错处理
                text = submitted.replace("T", " ")
                pub_date = text[:10]

            # PDF：fileMain_s 是直接 PDF URL（可能为字符串或数组）
            pdf_url = _first(doc.get("fileMain_s"))
            if pdf_url == "":
                pdf_url = None

            # 源 URL：优先 uri_s（HAL 详情页），缺失时基于 halId 构造
            uri = _first(doc.get("uri_s"))
            if uri:
                source_url = uri
            elif hal_id:
                source_url = f"https://hal.science/{hal_id}"
            else:
                source_url = "https://hal.science/"

            # 期刊：journalTitle_s 多为字符串
            journal = _first(doc.get("journalTitle_s")) or None

            # 外部链接（用于 raw 调试参考）
            ext_links = doc.get("linkExtUrl_s")
            if isinstance(ext_links, str):
                ext_links = [ext_links]

            doc_type = _first(doc.get("docType_s"))

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source="hal",
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # HAL 不提供引用数
                journal=journal,
                raw={
                    "hal_id": hal_id,
                    "doc_type": doc_type,
                    "external_links": ext_links,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 HAL doc 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        rows: int = 10,
    ) -> SearchResponse:
        """使用 Solr 查询语法搜索 HAL。

        Args:
            query: Solr 查询串，可使用字段限定（如 ``title_t:neural``）
                   或自然关键词（默认全文检索）。
            rows: 返回结果数量。

        Returns:
            SearchResponse 包含结果列表及分页信息。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "fl": _FIELDS,
            "rows": rows,
            "wt": "json",
            "sort": "score desc",
        }

        resp = await self._client.get("/search/", params=params)
        data: dict[str, Any] = resp.json()

        response_block = data.get("response") or {}
        docs = response_block.get("docs") or []
        total = response_block.get("numFound", len(docs))

        results: list[PaperResult] = []
        for doc in docs:
            try:
                results.append(self._parse_doc(doc))
            except ParseError as exc:
                logger.debug("跳过解析失败的 HAL doc: %s", exc)

        return SearchResponse(
            query=query,
            total_results=total,
            page=1,
            per_page=rows,
            results=results,
            source="hal",
        )


_ID = re.compile(r"^[a-z]+-\d+$")


class HalClientProtocol(Protocol):
    async def search(self, query: str, rows: int = 10) -> Any: ...


class HalSearchProvider(ClientSearchProvider):
    def __init__(self, client: HalClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, rows=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results = getattr(response, "results", None)
    total = getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "hal"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid HAL response")
    return SearchPage(
        items=tuple(_item(paper, index) for index, paper in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("hal",), succeeded=("hal",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = getattr(paper, "raw", {}).get("hal_id")
    parsed = urlsplit(getattr(paper, "source_url", ""))
    if (
        getattr(paper, "source", None) != "hal"
        or not isinstance(identifier, str)
        or _ID.fullmatch(identifier) is None
        or parsed.scheme != "https"
        or parsed.hostname not in {"hal.science", "hal.archives-ouvertes.fr"}
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.fragment
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid HAL identifier")
    return SearchItem(
        id=f"hal:{identifier}",
        title=paper.title.strip(),
        url=paper.source_url,
        snippet=paper.abstract,
        rank=rank,
        provenance=(Provenance(provider="hal", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=paper.year,
            authors=tuple(author.name for author in paper.authors),
            identifiers=(SearchIdentifier(scheme="hal", value=identifier),),
            resource_type=paper.raw.get("doc_type"),
        ),
    )


_SPEC = ClientSearchSpec("hal", "paper", _invoke, _project)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return HalSearchProvider(
        HalClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = HAL_PROVIDER_MANIFEST
SPEC = HAL_PROVIDER_SPEC
PROVIDER_TYPE = HalSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
