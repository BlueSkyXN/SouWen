"""Anonymous Figshare public article metadata client."""

from __future__ import annotations

from typing import Any

from souwen.core.exceptions import NotFoundError, ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    FundingReference,
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

_BASE_URL = "https://api.figshare.com/v2"
_MAX_PER_PAGE = 100
_TYPE_GENERAL = {
    "book": "Book",
    "book chapter": "BookChapter",
    "dataset": "Dataset",
    "figure": "Image",
    "fileset": "Collection",
    "journal contribution": "JournalArticle",
    "media": "Audiovisual",
    "online resource": "InteractiveResource",
    "poster": "Poster",
    "presentation": "Presentation",
    "preprint": "Preprint",
    "software": "Software",
    "thesis": "Dissertation",
}


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _mapping_list(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class FigshareClient:
    """Read public Figshare article metadata without following file URLs."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="figshare")

    async def __aenter__(self) -> "FigshareClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)

    @staticmethod
    def _article_id(value: object) -> str:
        if isinstance(value, bool):
            return ""
        normalized = str(value).strip() if isinstance(value, (int, str)) else ""
        return normalized if normalized.isdigit() and int(normalized) > 0 else ""

    @classmethod
    def _people(cls, value: object) -> list[ResearchContributor]:
        people: list[ResearchContributor] = []
        for item in _mapping_list(value):
            name = _string(item.get("full_name"))
            given_name = _string(item.get("first_name"))
            family_name = _string(item.get("last_name"))
            if name is None:
                name = " ".join(part for part in (given_name, family_name) if part) or None
            if name is None:
                continue
            identifiers: list[ResearchOutputIdentifier] = []
            if (orcid := _string(item.get("orcid_id"))) is not None:
                identifiers.append(ResearchOutputIdentifier(scheme="orcid", value=orcid))
            if author_id := cls._article_id(item.get("id")):
                identifiers.append(
                    ResearchOutputIdentifier(scheme="figshare_author_id", value=author_id)
                )
            people.append(
                ResearchContributor(
                    name=name,
                    given_name=given_name,
                    family_name=family_name,
                    identifiers=identifiers,
                )
            )
        return people

    @staticmethod
    def _subjects(record: dict[str, Any]) -> list[ResearchOutputSubject]:
        subjects: list[ResearchOutputSubject] = []
        for item in _mapping_list(record.get("categories")):
            title = _string(item.get("title"))
            if title is None:
                continue
            subjects.append(
                ResearchOutputSubject(
                    subject=title,
                    scheme="Figshare category",
                    classification_code=_string(item.get("id")),
                )
            )
        for tag in record.get("tags", []):
            if (value := _string(tag)) is not None:
                subjects.append(ResearchOutputSubject(subject=value, scheme="Figshare tag"))
        return subjects

    @staticmethod
    def _license(record: dict[str, Any]) -> tuple[list[RightsStatement], ResourceAccess]:
        license_data = record.get("license")
        name = _string(license_data.get("name")) if isinstance(license_data, dict) else None
        url = _string(license_data.get("url")) if isinstance(license_data, dict) else None
        rights = [RightsStatement(rights=name, rights_uri=url)] if name or url else []
        return rights, ResourceAccess(
            status="metadata_only",
            rights=name,
            license_url=url,
            notes=(
                "Figshare license and file URLs are source metadata only; SouWen does not verify "
                "access or download content."
            ),
        )

    @classmethod
    def _resources(
        cls, record: dict[str, Any], *, landing_url: str | None, access: ResourceAccess
    ) -> list[ResourceLink]:
        resources: list[ResourceLink] = []
        if landing_url:
            resources.append(
                ResourceLink(
                    url=landing_url,
                    relation="landing_page",
                    label="Figshare public article",
                    source="figshare",
                    access=access.model_copy(deep=True),
                )
            )
        for item in _mapping_list(record.get("files")):
            url = _string(item.get("download_url"))
            if url is None:
                continue
            link_only = (
                item.get("is_link_only") if isinstance(item.get("is_link_only"), bool) else None
            )
            file_name = _string(item.get("name"))
            resources.append(
                ResourceLink(
                    url=url,
                    relation="declared_file_url",
                    label="Figshare declared file metadata" + (" (link-only)" if link_only else ""),
                    file_name=file_name,
                    size_bytes=_positive_int(item.get("size")),
                    media_type=_string(item.get("mimetype")),
                    format=_string(item.get("mimetype")),
                    is_link_only=link_only,
                    source="figshare",
                    access=access.model_copy(
                        update={
                            "notes": (
                                "Figshare declared file URL; SouWen does not follow or verify "
                                "download access."
                            )
                        },
                        deep=True,
                    ),
                )
            )
        return resources

    @classmethod
    def _parse_record(cls, record: object) -> ResearchOutputResult:
        if not isinstance(record, dict):
            raise ParseError("Figshare record 不是对象")
        article_id = cls._article_id(record.get("id"))
        title = _string(record.get("title"))
        if not article_id or title is None:
            raise ParseError("Figshare record 缺少 id 或 title")
        resource_type = _string(record.get("defined_type_name"))
        normalized_type = resource_type.lower() if resource_type else ""
        rights_list, access = cls._license(record)
        landing_url = _string(record.get("url_public_html"))
        public_api_url = _string(record.get("url_public_api"))
        identifiers = [ResearchOutputIdentifier(scheme="figshare_article_id", value=article_id)]
        if (doi := _string(record.get("doi"))) is not None:
            identifiers.insert(0, ResearchOutputIdentifier(scheme="doi", value=doi))
        dates = [
            ResearchOutputDate(value=value, date_type=date_type)
            for key, date_type in (
                ("published_date", "Issued"),
                ("created_date", "Created"),
                ("modified_date", "Updated"),
            )
            if (value := _string(record.get(key))) is not None
        ]
        funding_references = [
            FundingReference(
                funder_name=_string(item.get("funder_name")) or _string(item.get("title")),
                funder_identifier=_string(item.get("id")),
                award_number=_string(item.get("grant_code")),
            )
            for item in _mapping_list(record.get("funding_list"))
        ]
        if not funding_references and (funding := _string(record.get("funding"))) is not None:
            funding_references = [FundingReference(funder_name=funding)]
        return ResearchOutputResult(
            source="figshare",
            source_record_id=article_id,
            title=title,
            titles=[title],
            creators=cls._people(record.get("authors")),
            dates=dates,
            subjects=cls._subjects(record),
            descriptions=[
                ResearchOutputDescription(value=description, description_type="Abstract")
                for description in [_string(record.get("description"))]
                if description is not None
            ],
            funding_references=funding_references,
            resource_type_general=_TYPE_GENERAL.get(
                normalized_type, "Other" if resource_type else None
            ),
            resource_type=resource_type,
            rights_list=rights_list,
            identifiers=identifiers,
            landing_url=landing_url,
            resources=cls._resources(record, landing_url=landing_url, access=access),
            access=access,
            source_url=landing_url or public_api_url or f"{_BASE_URL}/articles/{article_id}",
        )

    async def search(self, query: str, page_size: int = 10, page: int = 1) -> SearchResponse:
        """Search public article list metadata without detail fan-out."""
        normalized_query = query.strip()
        if not normalized_query or not 1 <= page_size <= _MAX_PER_PAGE or page < 1:
            raise ValueError(
                f"query 必须非空，page_size 必须在 1..{_MAX_PER_PAGE}，page 必须大于 0"
            )
        response = await self._client.post(
            "/articles/search",
            json={"search_for": normalized_query, "page": page, "page_size": page_size},
            headers={"Accept": "application/json"},
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise ParseError("Figshare search 响应不是列表")
        results: list[ResearchOutputResult] = []
        for record in payload:
            try:
                results.append(self._parse_record(record))
            except ParseError:
                continue
        return SearchResponse(
            query=normalized_query,
            source="figshare",
            results=results,
            page=page,
            per_page=page_size,
        )

    async def get_by_id(self, article_id: str | int) -> ResearchOutputResult:
        """Read one public article detail record, including declared file metadata only."""
        normalized_id = self._article_id(article_id)
        if not normalized_id:
            raise ValueError("article_id 必须是正整数")
        response = await self._client.get(f"/articles/{normalized_id}")
        if response.status_code == 404:
            raise NotFoundError(f"Figshare 未找到 article: {normalized_id}")
        return self._parse_record(response.json())
