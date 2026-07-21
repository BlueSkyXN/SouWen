"""Anonymous DataCite JSON:API client for research-output metadata."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
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
