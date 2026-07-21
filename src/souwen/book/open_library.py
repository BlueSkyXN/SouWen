"""Official Open Library Search, Works, Editions and Covers client.

The search endpoint returns work-level records.  It deliberately does not
follow every result with a work/edition request: callers that need bounded
edition metadata must explicitly call :meth:`get_by_work_id`.
"""

from __future__ import annotations

from typing import Any

from souwen.core.exceptions import ParseError
from souwen.core.http_client import SouWenHttpClient
from souwen.models import (
    Author,
    BookEdition,
    BookIdentifier,
    BookResult,
    ResourceAccess,
    ResourceLink,
    SearchResponse,
)

_BASE_URL = "https://openlibrary.org"
_COVERS_URL = "https://covers.openlibrary.org"
_SEARCH_FIELDS = ",".join(
    (
        "key",
        "title",
        "author_name",
        "first_publish_year",
        "publisher",
        "language",
        "subject",
        "isbn",
        "lccn",
        "oclc",
        "cover_i",
        "ia",
        "public_scan_b",
        "edition_count",
    )
)


class OpenLibraryClient:
    """Anonymous Open Library catalog client; no borrowing or downloads are performed."""

    def __init__(self) -> None:
        self._client = SouWenHttpClient(base_url=_BASE_URL, source_name="open_library")

    async def __aenter__(self) -> "OpenLibraryClient":
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
    def _strings(value: object, *, limit: int = 25) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()][:limit]

    @staticmethod
    def _language_codes(value: object) -> list[str]:
        values: list[object] = value if isinstance(value, list) else [value]
        codes: list[str] = []
        for item in values:
            if isinstance(item, str):
                code = item.removeprefix("/languages/").strip()
            elif isinstance(item, dict) and isinstance(item.get("key"), str):
                code = item["key"].removeprefix("/languages/").strip()
            else:
                continue
            if code:
                codes.append(code)
        return codes[:25]

    @staticmethod
    def _work_id(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.strip().removeprefix("/works/")
        return normalized if normalized.startswith("OL") and normalized.endswith("W") else ""

    @staticmethod
    def _edition_id(value: object) -> str:
        if not isinstance(value, str):
            return ""
        normalized = value.strip().removeprefix("/books/")
        return normalized if normalized.startswith("OL") and normalized.endswith("M") else ""

    @staticmethod
    def _identifiers(record: dict[str, Any], work_id: str) -> list[BookIdentifier]:
        identifiers: list[BookIdentifier] = [BookIdentifier(scheme="olid", value=work_id)]
        for scheme, field in (("isbn", "isbn"), ("lccn", "lccn"), ("oclc", "oclc")):
            for value in OpenLibraryClient._strings(record.get(field)):
                normalized = value.replace("-", "") if scheme == "isbn" else value
                if scheme == "isbn":
                    identifier_scheme = "isbn13" if len(normalized) == 13 else "isbn10"
                    if len(normalized) not in {10, 13}:
                        continue
                else:
                    identifier_scheme = scheme
                identifiers.append(BookIdentifier(scheme=identifier_scheme, value=value))
        return identifiers

    @staticmethod
    def _cover_resource(cover_id: object) -> ResourceLink | None:
        if not isinstance(cover_id, int) or cover_id <= 0:
            return None
        return ResourceLink(
            url=f"{_COVERS_URL}/b/id/{cover_id}-M.jpg?default=false",
            relation="cover",
            label="Open Library cover",
            media_type="image/jpeg",
            source="open_library",
            access=ResourceAccess(status="unknown", notes="Open Library Covers API resource"),
        )

    @staticmethod
    def _archive_resources(record: dict[str, Any]) -> list[ResourceLink]:
        resources: list[ResourceLink] = []
        for identifier in OpenLibraryClient._strings(record.get("ia"), limit=5):
            resources.append(
                ResourceLink(
                    url=f"https://archive.org/details/{identifier}",
                    relation="external_catalog_record",
                    label="Internet Archive record",
                    source="internet_archive",
                    access=ResourceAccess(
                        status="unknown",
                        notes="Catalog link only; SouWen does not borrow, read, or download it.",
                    ),
                )
            )
        return resources

    @classmethod
    def _parse_search_record(cls, record: dict[str, Any]) -> BookResult:
        work_id = cls._work_id(record.get("key"))
        title = record.get("title")
        if not work_id or not isinstance(title, str) or not title.strip():
            raise ParseError("Open Library search record 缺少 work key 或 title")
        resources = cls._archive_resources(record)
        cover = cls._cover_resource(record.get("cover_i"))
        if cover is not None:
            resources.insert(0, cover)
        first_publish_year = record.get("first_publish_year")
        return BookResult(
            source="open_library",
            source_record_id=work_id,
            title=title.strip(),
            authors=[Author(name=name) for name in cls._strings(record.get("author_name"))],
            languages=cls._strings(record.get("language")),
            subjects=cls._strings(record.get("subject")),
            publishers=cls._strings(record.get("publisher")),
            first_publish_year=first_publish_year if isinstance(first_publish_year, int) else None,
            identifiers=cls._identifiers(record, work_id),
            resources=resources,
            access=ResourceAccess(status="metadata_only"),
            source_url=f"{_BASE_URL}/works/{work_id}",
        )

    @staticmethod
    def _description(value: object) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            return value["value"].strip() or None
        return None

    @classmethod
    def _parse_edition(cls, record: dict[str, Any]) -> BookEdition:
        edition_id = cls._edition_id(record.get("key"))
        identifiers = []
        if edition_id:
            identifiers.append(BookIdentifier(scheme="olid", value=edition_id))
        for value in cls._strings(record.get("isbn")):
            compact = value.replace("-", "")
            if len(compact) in {10, 13}:
                identifiers.append(
                    BookIdentifier(scheme="isbn13" if len(compact) == 13 else "isbn10", value=value)
                )
        resources: list[ResourceLink] = []
        cover_ids = record.get("covers")
        for value in cover_ids[:1] if isinstance(cover_ids, list) else []:
            cover = cls._cover_resource(value)
            if cover is not None:
                resources.append(cover)
        page_count = record.get("number_of_pages")
        return BookEdition(
            olid=edition_id or None,
            publishers=cls._strings(record.get("publishers")),
            publication_date=record.get("publish_date")
            if isinstance(record.get("publish_date"), str)
            else None,
            formats=cls._strings(record.get("physical_format")),
            languages=cls._language_codes(record.get("languages")),
            page_count=page_count if isinstance(page_count, int) and page_count >= 0 else None,
            identifiers=identifiers,
            resources=resources,
        )

    async def search(self, query: str, per_page: int = 10, page: int = 1) -> SearchResponse:
        """Search work-level catalog records without edition-detail fan-out."""
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be within 1..100")
        if page < 1:
            raise ValueError("page must be greater than or equal to 1")
        response = await self._client.get(
            "/search.json",
            params={"q": query, "limit": per_page, "page": page, "fields": _SEARCH_FIELDS},
        )
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("docs"), list):
            raise ParseError("Open Library search 响应缺少 docs 列表")
        results: list[BookResult] = []
        for item in payload["docs"]:
            if not isinstance(item, dict):
                continue
            try:
                results.append(self._parse_search_record(item))
            except ParseError:
                continue
        total = payload.get("numFound")
        return SearchResponse(
            query=query,
            source="open_library",
            total_results=total if isinstance(total, int) and total >= 0 else None,
            page=page,
            per_page=per_page,
            results=results,
        )

    async def get_by_work_id(self, work_id: str, edition_limit: int = 5) -> BookResult:
        """Return one work plus a bounded sample of its editions."""
        if not 1 <= edition_limit <= 25:
            raise ValueError("edition_limit must be within 1..25")
        normalized = self._work_id(work_id)
        if not normalized:
            raise ValueError("work_id 必须是 Open Library work OLID")
        work_response = await self._client.get(f"/works/{normalized}.json")
        work = work_response.json()
        if not isinstance(work, dict):
            raise ParseError("Open Library work 响应不是对象")
        title = work.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ParseError("Open Library work 响应缺少 title")
        editions_response = await self._client.get(
            f"/works/{normalized}/editions.json", params={"limit": edition_limit}
        )
        editions_payload = editions_response.json()
        edition_rows = editions_payload.get("entries") if isinstance(editions_payload, dict) else []
        editions = [self._parse_edition(item) for item in edition_rows if isinstance(item, dict)]
        resources: list[ResourceLink] = []
        covers = work.get("covers")
        if isinstance(covers, list):
            for cover_id in covers[:1]:
                cover = self._cover_resource(cover_id)
                if cover is not None:
                    resources.append(cover)
        return BookResult(
            source="open_library",
            source_record_id=normalized,
            title=title.strip(),
            subjects=self._strings(work.get("subjects")),
            description=self._description(work.get("description")),
            identifiers=[BookIdentifier(scheme="olid", value=normalized)],
            editions=editions,
            resources=resources,
            access=ResourceAccess(status="metadata_only"),
            source_url=f"{_BASE_URL}/works/{normalized}",
        )
