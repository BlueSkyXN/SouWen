"""datacite（SPEC 7 单模块形态：声明 + 请求构造 + 解析 + 注册）。

源的全部定义在此：manifest/spec 声明、传输 client、Provider 桥与
``build_provider`` 注册入口。``server.v2_runtime`` 按目录发现本文件，
源目录之外没有按源 id 的业务分派。
"""

from __future__ import annotations

from collections.abc import Mapping
from souwen.common_runtime.channel_overrides import without_source_channel_overrides
from souwen.common_runtime.provider_support.exceptions import NotFoundError, ParseError
from souwen.common_runtime.provider_support.http_client import SouWenHttpClient
from souwen.config import SouWenConfig
from souwen.platform.provider_spec import ClientSearchProviderSpec, ClientTransportDeclaration
from souwen.platform.provider_spec.models import HttpOperation
from souwen.platform.provider_spec.research_output import ResearchOutputSearchProvider
from souwen.providers.runtime_clients.models import (
    FundingReference,
    RelatedIdentifier,
    ResearchContributor,
    ResearchOutputDate,
    ResearchOutputDescription,
    ResearchOutputIdentifier,
    ResearchOutputResult,
    ResearchOutputSubject,
    ResourceAccess,
    ResourceLink,
    RightsStatement,
    SearchResponse,
)
from typing import Any, Protocol
from urllib.parse import quote


from souwen.platform.manifest_registry import ProviderManifest


DATACITE_PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "schema_version": 2,
        "id": "datacite",
        "version": "2.0.0rc6",
        "contract_version": "provider-v2",
        "capabilities": ["search"],
        "adapters": [
            {
                "id": "datacite-search",
                "capability": "search",
                "export": "DataCiteSearchProvider",
                "availability": "configured",
            }
        ],
        "configuration": {
            "schema_reference": "datacite-provider-config-v1",
            "unknown_key_policy": "reject",
            "non_secret_keys": ["enabled"],
        },
        "secrets": {"references": []},
        "network": {
            "egress_hosts": ["api.datacite.org"],
            "min_egress": "impersonate",
            "max_egress": "proxy",
            "proxy_supported": True,
            "browser_required": False,
        },
        "risk": {"authenticated": False, "costed": False},
        "observability": {"dimensions": ["provider", "adapter", "capability", "outcome"]},
        "compatibility": {
            "contract_versions": ["provider-v2"],
            "config_schema_versions": ["datacite-provider-config-v1"],
        },
    }
)

__all__ = ["DATACITE_PROVIDER_MANIFEST"]


DATACITE_PROVIDER_SPEC = ClientSearchProviderSpec(
    provider_id="datacite",
    adapter_id="datacite-search",
    domain="paper",
    adapter_reason=(
        "DataCite's typed research-output projection retains metadata beyond the canonical Search DTO"
    ),
    transport=ClientTransportDeclaration(
        scheme="https",
        host="api.datacite.org",
        base_path="/",
        protocol="json",
        operations=(HttpOperation(method="GET", endpoint="/dois"),),
    ),
    configuration_keys=("enabled",),
)

__all__ = ["DATACITE_PROVIDER_SPEC"]


_BASE_URL = "https://api.datacite.org"

_MAX_PER_PAGE = 100


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: object) -> list[str]:
    return [_string(item) for item in value if _string(item)] if isinstance(value, list) else []


class DataCiteClient:
    """Read public findable DOI metadata; never follows landing or content URLs."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="datacite")

    async def __aenter__(self) -> "DataCiteClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _mapping_list(value: object) -> list[dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @classmethod
    def _identifiers(cls, attributes: dict[str, Any], doi: str) -> list[ResearchOutputIdentifier]:
        identifiers = [ResearchOutputIdentifier(scheme="doi", value=doi)]
        for item in cls._mapping_list(attributes.get("identifiers")) + cls._mapping_list(
            attributes.get("alternateIdentifiers")
        ):
            value = _string(item.get("identifier"))
            if value is None:
                continue
            identifiers.append(
                ResearchOutputIdentifier(
                    scheme=_string(item.get("identifierType")) or "other",
                    value=value,
                )
            )
        return identifiers

    @classmethod
    def _people(cls, value: object, *, contributors: bool = False) -> list[ResearchContributor]:
        people: list[ResearchContributor] = []
        for item in cls._mapping_list(value):
            name = _string(item.get("name"))
            if name is None:
                continue
            affiliations: list[str] = []
            for affiliation in item.get("affiliation", []):
                if isinstance(affiliation, dict):
                    normalized = _string(affiliation.get("name"))
                else:
                    normalized = _string(affiliation)
                if normalized:
                    affiliations.append(normalized)
            identifiers = [
                ResearchOutputIdentifier(
                    scheme=_string(identifier.get("nameIdentifierScheme")) or "other",
                    value=value,
                    url=_string(identifier.get("schemeUri")),
                )
                for identifier in cls._mapping_list(item.get("nameIdentifiers"))
                if (value := _string(identifier.get("nameIdentifier")))
            ]
            people.append(
                ResearchContributor(
                    name=name,
                    given_name=_string(item.get("givenName")),
                    family_name=_string(item.get("familyName")),
                    name_type=_string(item.get("nameType")),
                    contributor_type=_string(item.get("contributorType")) if contributors else None,
                    affiliations=affiliations,
                    identifiers=identifiers,
                )
            )
        return people

    @classmethod
    def _rights(cls, value: object) -> list[RightsStatement]:
        return [
            RightsStatement(
                rights=_string(item.get("rights")),
                rights_uri=_string(item.get("rightsUri")),
                rights_identifier=_string(item.get("rightsIdentifier")),
                rights_identifier_scheme=_string(item.get("rightsIdentifierScheme")),
                scheme_uri=_string(item.get("schemeUri")),
                language=_string(item.get("lang")),
            )
            for item in cls._mapping_list(value)
        ]

    @classmethod
    def _parse_record(cls, record: object) -> ResearchOutputResult:
        if not isinstance(record, dict):
            raise ParseError("DataCite record 不是对象")
        attributes = record.get("attributes")
        if not isinstance(attributes, dict):
            raise ParseError("DataCite record 缺少 attributes")
        doi = _string(attributes.get("doi")) or _string(record.get("id"))
        titles = [
            title
            for item in cls._mapping_list(attributes.get("titles"))
            if (title := _string(item.get("title")))
        ]
        if doi is None or not titles:
            raise ParseError("DataCite record 缺少 DOI 或 title")
        types = attributes.get("types") if isinstance(attributes.get("types"), dict) else {}
        landing_url = _string(attributes.get("url"))
        content_urls = _strings(attributes.get("contentUrl"))
        rights_list = cls._rights(attributes.get("rightsList"))
        resources: list[ResourceLink] = []
        if landing_url:
            resources.append(
                ResourceLink(
                    url=landing_url,
                    relation="landing_page",
                    label="DataCite landing page",
                    source="datacite",
                    access=ResourceAccess(status="metadata_only"),
                )
            )
        for content_url in content_urls:
            resources.append(
                ResourceLink(
                    url=content_url,
                    relation="content_url",
                    label="DataCite declared content URL",
                    source="datacite",
                    access=ResourceAccess(status="metadata_only"),
                )
            )
        publisher = attributes.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("name")
        return ResearchOutputResult(
            source="datacite",
            source_record_id=doi,
            title=titles[0],
            titles=titles,
            creators=cls._people(attributes.get("creators")),
            contributors=cls._people(attributes.get("contributors"), contributors=True),
            publisher=_string(publisher),
            publication_year=attributes.get("publicationYear")
            if isinstance(attributes.get("publicationYear"), int)
            else None,
            dates=[
                ResearchOutputDate(
                    value=value,
                    date_type=_string(item.get("dateType")),
                    information=_string(item.get("dateInformation")),
                )
                for item in cls._mapping_list(attributes.get("dates"))
                if (value := _string(item.get("date")))
            ],
            subjects=[
                ResearchOutputSubject(
                    subject=subject,
                    scheme=_string(item.get("subjectScheme")),
                    scheme_uri=_string(item.get("schemeUri")),
                    value_uri=_string(item.get("valueUri")),
                    language=_string(item.get("lang")),
                    classification_code=_string(item.get("classificationCode")),
                )
                for item in cls._mapping_list(attributes.get("subjects"))
                if (subject := _string(item.get("subject")))
            ],
            descriptions=[
                ResearchOutputDescription(
                    value=description,
                    description_type=_string(item.get("descriptionType")),
                    language=_string(item.get("lang")),
                )
                for item in cls._mapping_list(attributes.get("descriptions"))
                if (description := _string(item.get("description")))
            ],
            funding_references=[
                FundingReference(
                    funder_name=_string(item.get("funderName")),
                    funder_identifier=_string(item.get("funderIdentifier")),
                    funder_identifier_type=_string(item.get("funderIdentifierType")),
                    award_number=_string(item.get("awardNumber")),
                    award_uri=_string(item.get("awardUri")),
                    award_title=_string(item.get("awardTitle")),
                )
                for item in cls._mapping_list(attributes.get("fundingReferences"))
            ],
            resource_type_general=_string(types.get("resourceTypeGeneral")),
            resource_type=_string(types.get("resourceType")),
            rights_list=rights_list,
            related_identifiers=[
                RelatedIdentifier(
                    value=value,
                    identifier_type=_string(item.get("relatedIdentifierType")),
                    relation_type=_string(item.get("relationType")),
                    resource_type_general=_string(item.get("resourceTypeGeneral")),
                    related_metadata_scheme=_string(item.get("relatedMetadataScheme")),
                    scheme_uri=_string(item.get("schemeUri")),
                    scheme_type=_string(item.get("schemeType")),
                    relation_type_information=_string(item.get("relationTypeInformation")),
                )
                for item in cls._mapping_list(attributes.get("relatedIdentifiers"))
                if (value := _string(item.get("relatedIdentifier")))
            ],
            geo_locations=cls._mapping_list(attributes.get("geoLocations")),
            identifiers=cls._identifiers(attributes, doi),
            language=_string(attributes.get("language")),
            version=_string(attributes.get("version")),
            landing_url=landing_url,
            content_urls=content_urls,
            resources=resources,
            access=ResourceAccess(
                status="metadata_only",
                rights=next((item.rights for item in rights_list if item.rights), None),
                license_url=next(
                    (item.rights_uri for item in rights_list if item.rights_uri), None
                ),
                notes="DataCite rights and URLs are metadata only; SouWen does not verify access or download content.",
            ),
            source_url=landing_url or f"https://doi.org/{doi}",
        )

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        """Search public findable DOI metadata using documented page-number pagination."""
        if not query.strip() or not 1 <= per_page <= _MAX_PER_PAGE or page < 1:
            raise ValueError(f"query 必须非空，per_page 必须在 1..{_MAX_PER_PAGE}，page 必须大于 0")
        response = await self._client.get(
            "/dois",
            params={
                "query": query,
                "page[size]": str(per_page),
                "page[number]": str(page),
                "sort": "relevance",
                "disable-facets": "true",
            },
        )
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ParseError("DataCite 响应缺少 data 列表")
        results: list[ResearchOutputResult] = []
        for record in payload["data"]:
            try:
                results.append(self._parse_record(record))
            except ParseError:
                continue
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        total = meta.get("total") if isinstance(meta.get("total"), int) else None
        return SearchResponse(
            query=query,
            source="datacite",
            total_results=total,
            results=results,
            page=page,
            per_page=per_page,
        )

    async def get_by_doi(self, doi: str) -> ResearchOutputResult:
        """Read one DOI record with affiliation and publisher object shapes enabled."""
        normalized = doi.strip()
        if not normalized:
            raise ValueError("doi 必须非空")
        try:
            response = await self._client.get(
                f"/dois/{quote(normalized, safe='/')}",
                params={"affiliation": "true", "publisher": "true"},
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                raise NotFoundError(f"DataCite 未找到 DOI: {normalized}") from exc
            raise
        payload = response.json()
        if not isinstance(payload, dict):
            raise ParseError("DataCite detail 响应不是对象")
        return self._parse_record(payload.get("data"))


class DataCiteClientProtocol(Protocol):
    async def search(self, query: str, per_page: int = 10, page: int = 1) -> Any: ...
    async def close(self) -> None: ...


class DataCiteSearchProvider(ResearchOutputSearchProvider):
    def __init__(self, client: DataCiteClientProtocol, *, enabled: bool = True) -> None:
        super().__init__(client, provider_id="datacite", limit_keyword="per_page", enabled=enabled)


__all__ = ["DataCiteClientProtocol", "DataCiteSearchProvider"]


def build_provider(
    configuration: Mapping[str, object],
    secrets: Mapping[str, str],
    config: SouWenConfig,
    reviewed_proxy: str | None,
) -> Any:
    del secrets  # 零 Key
    from souwen.server.v2_runtime import _RuntimeClientAdapter

    with without_source_channel_overrides(
        proxy=reviewed_proxy,
        timeout_seconds=config.timeout,
        max_retries=config.max_retries,
    ):
        client = DataCiteClient()
    return DataCiteSearchProvider(
        _RuntimeClientAdapter(client),
        enabled=bool(configuration["enabled"]),
    )


MANIFEST = DATACITE_PROVIDER_MANIFEST
SPEC = DATACITE_PROVIDER_SPEC
PROVIDER_TYPE = DataCiteSearchProvider


__all__ = ["MANIFEST", "PROVIDER_TYPE", "SPEC", "build_provider"]
