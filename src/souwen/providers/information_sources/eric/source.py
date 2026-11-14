"""eric（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

from collections.abc import Mapping
from souwen.common_runtime.provider_support.exceptions import ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.common_runtime.transport import HttpTransport
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import RestJsonProviderSpec, RestJsonSearchProvider
from souwen.platform.provider_spec.models import (
    HttpOperation,
    SearchRequestMapping,
    SearchResponseMapping,
)
from souwen.providers.runtime_clients.models import Author, PaperResult, SearchResponse
from typing import Any, Protocol


from souwen.platform.manifest_registry import ProviderManifest


ERIC_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "eric",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "eric-search",
                "capability": "search",
                "export": "EricSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "eric-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled", "max_retries", "timeout_seconds"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.ies.ed.gov"],
            "min_egress": "impersonate",
            "max_egress": "impersonate",
            "proxy_supported": False,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["eric-provider-config-v1"],
        },
    }
)


__all__ = ["ERIC_PROVIDER_MANIFEST"]


ERIC_REST_SPEC = RestJsonProviderSpec(
    provider_id="eric",
    adapter_id="eric-search",
    host="api.ies.ed.gov",
    base_path="/",
    operation=HttpOperation(method="GET", endpoint="/eric/"),
    request_mapping=SearchRequestMapping(
        query_field="query", limit_field="rows", fixed_fields={"start": 0}
    ),
    response_mapping=SearchResponseMapping(
        source_field="source",
        items_field="results",
        total_field="total_results",
        page_field="page",
        limit_field="per_page",
        item_source_field="source",
        identifier_path="raw.eric_id",
        identifier_pattern=r"[A-Z]{2}[0-9]+",
        identifier_scheme="eric",
        identifier_normalization="upper",
        title_path="title",
        snippet_path="abstract",
        year_path="year",
        authors_path="authors",
        author_name_path="name",
        resource_type_path="raw.publication_types",
        language_path="raw.language",
        open_access_path="raw.fulltext_authorized",
        record_url_path="source_url",
        record_host="eric.ed.gov",
        record_path_template="/",
        record_query_template="id={identifier}",
    ),
    configuration_keys=("enabled", "max_retries", "timeout_seconds"),
)

__all__ = ["ERIC_REST_SPEC"]


_BASE_URL = "https://api.ies.ed.gov"

_RECORD_URL = "https://eric.ed.gov/?id="

_FULLTEXT_URL = "https://files.eric.ed.gov/fulltext/"


class EricClient:
    """Search the official ERIC education-research metadata API without credentials."""

    def __init__(self, transport: HttpTransport | None = None) -> None:
        # Existing callers retain source-channel config resolution. Provider v2
        # injects an explicit Common Runtime transport from its resolved namespace.
        self._client = transport or SouWenHttpClient(base_url=_BASE_URL, source_name="eric")

    async def __aenter__(self) -> EricClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def close(self) -> None:
        """Close the owned transport through a public lifecycle operation."""
        await self._client.close()

    @staticmethod
    def _as_strings(value: object) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return []

    @staticmethod
    def _publication_year(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_record(record: dict[str, Any]) -> PaperResult:
        """Normalize one ERIC API document without inferring unavailable metadata."""
        record_id = record.get("id") if isinstance(record.get("id"), str) else ""
        title = record.get("title") if isinstance(record.get("title"), str) else ""
        authors = [Author(name=name) for name in EricClient._as_strings(record.get("author"))]
        description = record.get("description")
        abstract = (
            description.strip() if isinstance(description, str) and description.strip() else None
        )
        fulltext_authorized = record.get("e_fulltextauth") in {1, "1"}
        pdf_url = (
            f"{_FULLTEXT_URL}{record_id}.pdf"
            if fulltext_authorized and record_id.startswith("ED")
            else None
        )

        return PaperResult(
            source="eric",
            title=title,
            authors=authors,
            abstract=abstract,
            year=EricClient._publication_year(record.get("publicationdateyear")),
            journal=record.get("source") if isinstance(record.get("source"), str) else None,
            pdf_url=pdf_url,
            source_url=f"{_RECORD_URL}{record_id}" if record_id else "https://eric.ed.gov/",
            raw={
                "eric_id": record_id or None,
                "publication_types": EricClient._as_strings(record.get("publicationtype")),
                "subjects": EricClient._as_strings(record.get("subject")),
                "isbn": EricClient._as_strings(record.get("isbn")),
                "issn": EricClient._as_strings(record.get("issn")),
                "language": EricClient._as_strings(record.get("language")),
                "peer_reviewed": record.get("peerreviewed"),
                "publisher": record.get("publisher")
                if isinstance(record.get("publisher"), str)
                else None,
                "citation": record.get("sourceid")
                if isinstance(record.get("sourceid"), str)
                else None,
                "external_url": record.get("url") if isinstance(record.get("url"), str) else None,
                "fulltext_authorized": fulltext_authorized,
            },
        )

    async def search(
        self,
        query: str,
        rows: int = 10,
        start: int = 0,
    ) -> SearchResponse:
        """Search ERIC records using the documented offset pagination parameters."""
        if not 1 <= rows <= 2_000:
            raise ValueError("rows must be within 1..2000")
        if start < 0:
            raise ValueError("start must be greater than or equal to 0")

        response = await self._client.get(
            "/eric/",
            params={"search": query, "format": "json", "start": str(start), "rows": str(rows)},
        )
        payload = response.json()
        body = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            raise ParseError("ERIC 响应缺少 response 对象")
        documents = body.get("docs")
        if not isinstance(documents, list):
            raise ParseError("ERIC 响应 docs 字段不是列表")

        results = [self._parse_record(item) for item in documents if isinstance(item, dict)]
        total = body.get("numFound")
        total_results = total if isinstance(total, int) else None
        return SearchResponse(
            query=query,
            source="eric",
            total_results=total_results,
            page=(start // rows) + 1,
            per_page=rows,
            results=results,
        )


class EricClientProtocol(Protocol):
    async def search(self, query: str, rows: int = 10, start: int = 0) -> Any: ...
    async def close(self) -> None: ...


class EricSearchProvider(RestJsonSearchProvider):
    def __init__(self, client: EricClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, ERIC_REST_SPEC, enabled=enabled)


__all__ = ["EricClientProtocol", "EricSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del reviewed_proxy  # REST 固定端点，无通道覆盖
    from souwen.platform.provider_spec import resolve_provider_inputs
    from souwen.platform.provider_spec.validation import validate_spec_manifest

    validate_spec_manifest(ERIC_REST_SPEC, ERIC_PROVIDER_MANIFEST)
    resolved_configuration, resolved_secrets = resolve_provider_inputs(
        ERIC_REST_SPEC, configuration, secrets
    )
    headers = {"User-Agent": "SouWen/3.0.0a1"}
    transport = HttpTransport(
        base_url=ERIC_REST_SPEC.base_url,
        headers=headers,
        timeout=resolved_configuration["timeout_seconds"],
        max_retries=resolved_configuration["max_retries"],
        proxy=None,
        follow_redirects=False,
    )
    return EricSearchProvider(
        EricClient(transport=transport), enabled=resolved_configuration["enabled"]
    )


def resolve_configuration(config: SouWenConfig) -> dict[str, object]:
    if not config.is_source_enabled("eric", default=True):
        raise ValueError("provider is disabled")
    source = config.get_source_config("eric")
    from datetime import timedelta

    timeout = source.timeout or config.timeout
    max_retries = config.max_retries
    _ = timedelta  # noqa: F841 — 语义占位（spec 配置校验在 spec 层完成）
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not 0 < timeout <= 120
        or not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or not 0 <= max_retries <= 10
    ):
        raise ValueError("invalid ERIC transport configuration")
    return {"enabled": True, "max_retries": max_retries, "timeout_seconds": timeout}


MANIFEST = ERIC_PROVIDER_MANIFEST
SPEC = ERIC_REST_SPEC
PROVIDER_TYPE = EricSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
