"""zenodo（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

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


from souwen.platform.manifest_registry import ProviderManifest

ZENODO_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "zenodo",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "zenodo-search",
                "capability": "search",
                "export": "ZenodoSearchProvider",
                "availability": "always",
            }
        ],
        "configuration": {
            "schema_reference": "zenodo-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": [], "optional_references": ["ZENODO_ACCESS_TOKEN"]},
        "network": {
            "egress_hosts": ["zenodo.org"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["zenodo-provider-config-v1"],
        },
    }
)


ZENODO_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="zenodo",
    adapter_id="zenodo-search",
    adapter_reason="record identity and existing total normalization require a bridge",
    transport=ClientTransportDeclaration(
        host="zenodo.org",
        base_path="/api",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/records"),),
    ),
    auth=AuthDeclaration(
        placement="bearer",
        reference="ZENODO_ACCESS_TOKEN",
        field_name="Authorization",
        required=False,
    ),
    configuration_keys=("enabled",),
)


logger = logging.getLogger(__name__)

_BASE_URL = "https://zenodo.org/api"

_RECORDS_URL = "https://zenodo.org/records"

_DEFAULT_RPS = 5.0

_HTML_TAG_RE = re.compile(r"<[^>]+>")


class ZenodoClient:
    """Zenodo 开放科学仓库出版物搜索客户端。

    特点:
        - CERN 维护的开放科学仓库，覆盖 preprint、期刊文章、报告等
        - 默认仅检索出版物（type=publication），过滤数据集/软件/海报
        - 提供文件下载链接，可直接获取 PDF
        - 不提供引用计数
        - Access Token 可选，匿名访问也可用
    """

    def __init__(self, access_token: str | None = None) -> None:
        """初始化 Zenodo 客户端。

        Args:
            access_token: Zenodo Personal Access Token（可选）。未提供时
                          从全局配置读取，仍未配置则匿名访问。
        """
        cfg = get_config()
        self.access_token: str | None = access_token or cfg.resolve_api_key(
            "zenodo", "zenodo_access_token"
        )

        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        self._client = SouWenHttpClient(
            base_url=_BASE_URL,
            headers=headers,
            source_name="zenodo",
        )
        self._limiter = TokenBucketLimiter(rate=_DEFAULT_RPS, burst=_DEFAULT_RPS)

    # ------------------------------------------------------------------
    # async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ZenodoClient:
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
    def _strip_html(text: str) -> str:
        """剥离字符串中的 HTML 标签。

        Zenodo description 字段常含 <p>、<br>、<a> 等 HTML 标签，
        此处简单去除以获得纯文本摘要。

        Args:
            text: 可能含 HTML 标签的字符串。

        Returns:
            去除标签后的文本。
        """
        if not text:
            return ""
        return _HTML_TAG_RE.sub("", text).strip()

    @staticmethod
    def _parse_record(record: dict[str, Any]) -> PaperResult:
        """将 Zenodo record 转换为 PaperResult。

        Zenodo 响应结构：
        {
            "id": 12345,
            "metadata": {
                "title": "...",
                "creators": [{"name": "Doe, John"}, ...],
                "description": "<p>HTML abstract</p>",
                "publication_date": "2024-01-15",
                "doi": "10.5281/zenodo.12345",
                "keywords": [...],
                "license": {"id": "..."},
                "resource_type": {"type": "publication", "subtype": "article"}
            },
            "files": [{"key": "paper.pdf", "links": {"self": "..."}}],
            "links": {"html": "https://zenodo.org/records/12345"}
        }

        Args:
            record: Zenodo API 单条 record 对象。

        Returns:
            统一的 PaperResult 模型。

        Raises:
            ParseError: 解析关键字段失败时抛出。
        """
        try:
            metadata: dict[str, Any] = record.get("metadata", {}) or {}
            record_id = record.get("id", "")
            links: dict[str, Any] = record.get("links", {}) or {}

            title: str = metadata.get("title", "") or ""

            # 作者：creators[].name 通常为 "Last, First"，原样保留
            authors: list[Author] = []
            for creator in metadata.get("creators", []) or []:
                name = creator.get("name", "") if isinstance(creator, dict) else str(creator)
                if name:
                    authors.append(Author(name=name))

            # 摘要：去除 HTML 标签
            abstract = ZenodoClient._strip_html(metadata.get("description", "") or "") or None

            # DOI
            doi: str | None = metadata.get("doi") or None

            # 出版日期：YYYY-MM-DD
            pub_date: str | None = metadata.get("publication_date") or None
            year: int | None = None
            if pub_date and len(pub_date) >= 4:
                try:
                    year = int(pub_date[:4])
                except ValueError:
                    year = None

            # 文件：找首个 .pdf 文件
            pdf_url: str | None = None
            for f in record.get("files", []) or []:
                if not isinstance(f, dict):
                    continue
                key = (f.get("key") or "").lower()
                if not key.endswith(".pdf"):
                    continue
                file_links = f.get("links", {}) or {}
                pdf_url = file_links.get("self") or file_links.get("download")
                if pdf_url:
                    break

            # 详情页 URL
            source_url: str = links.get("html") or (
                f"{_RECORDS_URL}/{record_id}" if record_id else _RECORDS_URL
            )

            # license / resource_type 提取
            license_obj = metadata.get("license") or {}
            license_id = license_obj.get("id") if isinstance(license_obj, dict) else license_obj
            resource_type = metadata.get("resource_type") or {}
            resource_subtype = (
                resource_type.get("subtype") if isinstance(resource_type, dict) else None
            )

            return PaperResult(
                title=title,
                authors=authors,
                abstract=abstract,
                doi=doi,
                year=year,
                publication_date=pub_date,
                source="zenodo",  # type: ignore[arg-type]
                source_url=source_url,
                pdf_url=pdf_url,
                citation_count=None,  # Zenodo 不提供引用数
                raw={
                    "zenodo_id": record_id,
                    "keywords": metadata.get("keywords") or [],
                    "access_right": metadata.get("access_right"),
                    "license": license_id,
                    "resource_subtype": resource_subtype,
                },
            )
        except Exception as exc:
            raise ParseError(f"解析 Zenodo record 失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        size: int = 10,
    ) -> SearchResponse:
        """搜索 Zenodo 出版物。

        默认追加 type=publication 过滤，仅返回出版物（排除数据集、
        软件、海报、视频等非论文资源）。结果按最新发布排序。

        Args:
            query: 检索关键词，支持 Elasticsearch 查询语法。
            size: 返回条数。

        Returns:
            SearchResponse 包含结果列表及总数。
        """
        await self._limiter.acquire()

        params: dict[str, str | int] = {
            "q": query,
            "size": size,
            "sort": "mostrecent",
            "type": "publication",  # 关键过滤：仅出版物
        }

        resp = await self._client.get("/records", params=params)
        data: dict[str, Any] = resp.json()

        hits_obj: dict[str, Any] = data.get("hits", {}) or {}
        records = hits_obj.get("hits", []) or []

        # total 在不同 API 版本下可能为 int 或 {"value": int}
        total_raw = hits_obj.get("total", len(records))
        if isinstance(total_raw, dict):
            total = int(total_raw.get("value", len(records)))
        else:
            try:
                total = int(total_raw)
            except (ValueError, TypeError):
                total = len(records)

        results: list[PaperResult] = []
        for record in records:
            try:
                results.append(self._parse_record(record))
            except ParseError as exc:
                logger.debug("跳过解析失败的 Zenodo record: %s", exc)

        return SearchResponse(
            query=query,
            total_results=total,
            page=1,
            per_page=size,
            results=results,
            source="zenodo",  # type: ignore[arg-type]
        )


_ID = re.compile(r"^[1-9][0-9]*$")


class ZenodoClientProtocol(Protocol):
    async def search(self, query: str, size: int = 10) -> Any: ...


class ZenodoSearchProvider(ClientSearchProvider):
    def __init__(self, client: ZenodoClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, size=limit)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if (
        getattr(response, "source", None) != "zenodo"
        or getattr(response, "page", None) != 1
        or getattr(response, "per_page", None) != limit
        or not isinstance(results, Sequence)
        or isinstance(results, (str, bytes))
        or len(results) > limit
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
    ):
        raise ValueError("invalid Zenodo response")
    return SearchPage(
        items=tuple(_item(item, rank) for rank, item in enumerate(results, 1)),
        page=PageInfo(limit=limit, total=total),
        meta=SearchMeta(requested=("zenodo",), succeeded=("zenodo",)),
        context=context,
    )


def _item(paper: Any, rank: int) -> SearchItem:
    identifier = str(getattr(paper, "raw", {}).get("zenodo_id", ""))
    if (
        getattr(paper, "source", None) != "zenodo"
        or _ID.fullmatch(identifier) is None
        or not isinstance(getattr(paper, "title", None), str)
        or not paper.title.strip()
    ):
        raise ValueError("invalid Zenodo item")
    return SearchItem(
        id=f"zenodo:{identifier}",
        title=paper.title.strip(),
        url=f"https://zenodo.org/records/{identifier}",
        snippet=_text(paper.abstract),
        rank=rank,
        provenance=(Provenance(provider="zenodo", attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=_year(paper.year),
            authors=_authors(paper),
            identifiers=(SearchIdentifier(scheme="zenodo", value=identifier),),
            resource_type=_text(getattr(paper, "raw", {}).get("resource_subtype")),
        ),
    )


def _text(v: Any) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str) or not v.strip():
        raise ValueError("invalid text")
    return v.strip()


def _year(v: Any) -> int | None:
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 9999:
        raise ValueError("invalid year")
    return v


def _authors(paper: Any) -> tuple[str, ...]:
    values = tuple(_text(getattr(author, "name", None)) for author in getattr(paper, "authors", ()))
    if any(value is None for value in values) or len(set(values)) != len(values):
        raise ValueError("invalid authors")
    return tuple(value for value in values if value is not None)


_SPEC = ClientSearchSpec("zenodo", "paper", _invoke, _project)


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del config, reviewed_proxy
    return ZenodoSearchProvider(
        ZenodoClient(access_token=secrets.get("ZENODO_ACCESS_TOKEN")),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = ZENODO_PROVIDER_MANIFEST
SPEC = ZENODO_PROVIDER_SPEC
PROVIDER_TYPE = ZenodoSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
