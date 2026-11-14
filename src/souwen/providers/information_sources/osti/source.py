"""osti（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from souwen.common_runtime.provider_support.exceptions import NotFoundError, ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
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


OSTI_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "osti",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "osti-search",
                "capability": "search",
                "export": "OstiSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "osti-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["www.osti.gov"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["osti-provider-config-v1"],
        },
    }
)

__all__ = ["OSTI_PROVIDER_MANIFEST"]


OSTI_BRIDGE_SPEC = ClientSearchProviderSpec(
    provider_id="osti",
    adapter_id="osti-search",
    adapter_reason="OSTI total metadata is an HTTP header and the existing client owns list-response parsing",
    transport=ClientTransportDeclaration(
        scheme="https",
        host="www.osti.gov",
        base_path="/api/v1",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/records"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["OSTI_BRIDGE_SPEC"]


_BASE_URL = "https://www.osti.gov"

_RECORD_URL = "https://www.osti.gov/biblio/"

_YEAR_RE = re.compile(r"^(\d{4})")

_OSTI_ID_RE = re.compile(r"^\d+$")


class OstiClient:
    """Query OSTI.GOV's official, credential-free records API."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="osti")

    async def __aenter__(self) -> OstiClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def _as_text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    @staticmethod
    def _as_strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @classmethod
    def _authors(cls, value: object) -> list[Author]:
        """Normalize the documented string records and tolerate name mappings."""
        if not isinstance(value, list):
            return [Author(name=name) for name in cls._as_strings(value)]

        authors: list[Author] = []
        for item in value:
            if isinstance(item, str):
                name = cls._as_text(item)
            elif isinstance(item, Mapping):
                name = cls._as_text(item.get("name"))
                if name is None:
                    parts = [
                        cls._as_text(item.get(field))
                        for field in ("first_name", "middle_name", "last_name")
                    ]
                    name = " ".join(part for part in parts if part) or None
            else:
                name = None
            if name:
                authors.append(Author(name=name))
        return authors

    @classmethod
    def _parse_record(cls, record: Mapping[str, Any]) -> PaperResult:
        """Normalize one OSTI record without inferring rights from resource links."""
        osti_id = cls._as_text(record.get("osti_id"))
        publication_date = cls._as_text(record.get("publication_date"))
        year_match = _YEAR_RE.match(publication_date or "")

        links = record.get("links")
        resource_links = (
            [item for item in links if isinstance(item, Mapping)] if isinstance(links, list) else []
        )

        return PaperResult(
            source="osti",
            title=cls._as_text(record.get("title")) or "",
            authors=cls._authors(record.get("authors")),
            abstract=cls._as_text(record.get("description")),
            doi=cls._as_text(record.get("doi")),
            year=int(year_match.group(1)) if year_match else None,
            publication_date=publication_date,
            source_url=f"{_RECORD_URL}{osti_id}" if osti_id else "https://www.osti.gov/",
            raw={
                "osti_id": osti_id,
                "product_type": cls._as_text(record.get("product_type")),
                "subjects": cls._as_strings(record.get("subjects")),
                "sponsor_orgs": cls._as_strings(record.get("sponsor_orgs")),
                "research_orgs": cls._as_strings(record.get("research_orgs")),
                # Keep the official relation/href data.  Its presence alone says nothing
                # about license, open-access status, or redistribution permission.
                "resource_links": [dict(item) for item in resource_links],
            },
        )

    @staticmethod
    def _records(payload: object, *, context: str) -> list[Mapping[str, Any]]:
        if not isinstance(payload, list):
            raise ParseError(f"OSTI {context} 响应不是 records 数组")
        if not all(isinstance(item, Mapping) for item in payload):
            raise ParseError(f"OSTI {context} records 包含非对象项")
        return payload

    async def search(self, query: str, rows: int = 10, page: int = 1) -> SearchResponse:
        """Search official OSTI records using ``q``, ``rows`` and ``page``."""
        query = query.strip() if isinstance(query, str) else ""
        if not query:
            raise ValueError("query must be a non-empty string")
        if rows < 1:
            raise ValueError("rows must be greater than or equal to 1")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")

        response = await self._client.get(
            "/api/v1/records",
            params={"q": query, "rows": str(rows), "page": str(page)},
        )
        records = self._records(response.json(), context="search")
        total_value = response.headers.get("x-total-count")
        try:
            total_results = int(total_value) if total_value is not None else len(records)
        except ValueError:
            total_results = len(records)

        return SearchResponse(
            query=query,
            source="osti",
            total_results=total_results,
            page=page,
            per_page=rows,
            results=[self._parse_record(record) for record in records],
        )

    async def get_by_id(self, osti_id: str) -> PaperResult:
        """Fetch and normalize one OSTI record by its official identifier."""
        normalized_id = osti_id.strip() if isinstance(osti_id, str) else ""
        if not _OSTI_ID_RE.fullmatch(normalized_id):
            raise ValueError("osti_id must be a non-empty numeric OSTI record ID")

        response = await self._client.get(f"/api/v1/records/{normalized_id}")
        if response.status_code == 404:
            raise NotFoundError(f"OSTI 未找到 ID: {normalized_id}")
        records = self._records(response.json(), context="detail")
        if not records:
            raise NotFoundError(f"OSTI 未找到 ID: {normalized_id}")
        return self._parse_record(records[0])


_PROVIDER_ID = "osti"


class OstiClientProtocol(Protocol):
    async def search(self, query: str, rows: int = 10, page: int = 1) -> Any: ...
    async def close(self) -> None: ...


class OstiSearchProvider(ClientSearchProvider):
    capability = "search"

    def __init__(self, client: OstiClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, _BRIDGE_SPEC, enabled=enabled)


async def _invoke(client: Any, request: SearchRequest, limit: int) -> Any:
    return await client.search(request.query, rows=limit, page=1)


def _project(response: Any, limit: int, context: RequestContext) -> SearchPage:
    if getattr(response, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing response source")
    results, total = getattr(response, "results", None), getattr(response, "total_results", None)
    if not isinstance(results, Sequence) or isinstance(results, (str, bytes)):
        raise ValueError("invalid OSTI search results")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < len(results)
        or len(results) > limit
    ):
        raise ValueError("invalid OSTI result total")
    if getattr(response, "page", None) != 1 or getattr(response, "per_page", None) != limit:
        raise ValueError("existing OSTI page does not match canonical request")
    return SearchPage(
        items=tuple(_item(value, index) for index, value in enumerate(results, 1)),
        page=PageInfo(limit=limit, next_cursor=None, total=total),
        meta=SearchMeta(requested=(_PROVIDER_ID,), succeeded=(_PROVIDER_ID,)),
        context=context,
    )


def _item(value: Any, rank: int) -> SearchItem:
    if getattr(value, "source", None) != _PROVIDER_ID:
        raise ValueError("unexpected existing OSTI paper source")
    raw = getattr(value, "raw", None)
    identifier = raw.get("osti_id") if isinstance(raw, dict) else None
    if not isinstance(identifier, str) or not identifier.isdecimal():
        raise ValueError("invalid OSTI record identifier")
    parsed = urlsplit(_text(getattr(value, "source_url", None)))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.osti.gov"
        or parsed.path != f"/biblio/{identifier}"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid OSTI record URL")
    year = getattr(value, "year", None)
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or not 0 <= year <= 9999
    ):
        raise ValueError("invalid OSTI year")
    authors = tuple(
        _text(getattr(author, "name", None)) for author in getattr(value, "authors", ())
    )
    if len(authors) != len(set(authors)):
        raise ValueError("duplicate OSTI authors")
    return SearchItem(
        id=f"osti:{identifier}",
        title=_text(getattr(value, "title", None)),
        url=f"https://www.osti.gov/biblio/{identifier}",
        snippet=_optional_text(getattr(value, "abstract", None)),
        rank=rank,
        provenance=(Provenance(provider=_PROVIDER_ID, attempt=1, outcome="success"),),
        attributes=SearchAttributes(
            year=year,
            authors=authors,
            identifiers=(SearchIdentifier(scheme="osti", value=identifier),),
            resource_type=_optional_text(raw.get("product_type")),
        ),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid text")
    return value.strip()


def _text(value: Any) -> str:
    result = _optional_text(value)
    if result is None:
        raise ValueError("missing text")
    return result


_BRIDGE_SPEC = ClientSearchSpec(_PROVIDER_ID, "paper", _invoke, _project)

assert OSTI_BRIDGE_SPEC.adapter_kind == "client_adapter"

__all__ = ["OstiClientProtocol", "OstiSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets, config, reviewed_proxy  # 零 Key、无通道覆盖
    return OstiSearchProvider(
        OstiClient(),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = OSTI_PROVIDER_MANIFEST
SPEC = OSTI_BRIDGE_SPEC
PROVIDER_TYPE = OstiSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
